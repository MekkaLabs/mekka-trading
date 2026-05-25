"""Atomic JSON write helper — protege contra corrupção em crash mid-write.

Padrão write-temp + os.replace: o arquivo de destino só é substituído
quando o conteúdo completo está em disco. Em POSIX, ``os.replace()`` é
atômico — uma leitura concorrente sempre vê o arquivo antigo OU o novo,
nunca um arquivo parcialmente escrito.

Antes (perigoso):
    path.write_text(json.dumps(data))
    # Se o processo crashar no meio do write, o arquivo fica truncado
    # ou corrompido — _load_index/_load_store retornam {} no próximo boot.

Depois (seguro):
    atomic_write_json(path, data)
    # O arquivo de destino só muda após o conteúdo completo em disco.
    # Crash no meio deixa o tmpfile órfão (silencioso, cleanup no boot).

Background: identificado na auditoria de integrações (G1, 2026-05-25).
Aplica-se a todos os JSON-state stores em data/ (improvement_queue,
improvement_prs, sage_baselines, portfolio_snapshot_cache, etc).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger


def atomic_write_json(
    path: Path | str,
    data: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    encoding: str = "utf-8",
) -> bool:
    """Write ``data`` as JSON to ``path`` atomically.

    Returns True on success, False on any failure (and logs a warning —
    never raises). The destination file is replaced only after the new
    content is fully on disk.

    Implementation:
      1. Serialize ``data`` to a string in memory (fails fast on bad types)
      2. Create a NamedTemporaryFile in the SAME directory (cross-device
         rename would fail if tmp is on a different filesystem)
      3. Write + flush + fsync to ensure bytes are on disk
      4. os.replace() — atomic on POSIX, best-effort on Windows
      5. On any error, attempt to delete the tmpfile
    """
    target = Path(path)
    try:
        payload = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError) as exc:
        logger.warning(f"[atomic_json] serialize failed for {target}: {exc}")
        return False

    # Ensure parent dir exists (matches the implicit guarantee of write_text).
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning(f"[atomic_json] could not create parent for {target}: {exc}")
        return False

    tmp_path: Path | None = None
    try:
        # delete=False so we control when to remove; mode='w' for text.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as tf:
            tmp_path = Path(tf.name)
            tf.write(payload)
            tf.flush()
            try:
                os.fsync(tf.fileno())
            except OSError:
                # fsync can fail on some FS (e.g., tmpfs); not critical for
                # atomicity, just for durability after a crash.
                pass
        # os.replace is atomic on POSIX. On Windows it overwrites existing
        # files (since 3.3) but is not guaranteed atomic on all FS.
        os.replace(str(tmp_path), str(target))
        return True
    except (OSError, IOError) as exc:
        logger.warning(f"[atomic_json] write failed for {target}: {exc}")
        # Best-effort cleanup of the orphan tmpfile.
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return False
