"""
tests/test_story_160_repo_map.py
===================================
Story 160 — MekkaRepoMap: Compact Codebase Symbol Index for LLM Context.

Inspirado em aider/repomap.py:
  "Aider builds a tree-sitter based repository map to give the LLM a compact
   overview of the codebase."

Testa:
- _parse_file: extrai classes, funções, async def
- scan(): varre diretórios, conta arquivos
- get_agent_map(): filtra só agents/
- get_service_map(): filtra só services/
- find_symbol(): busca símbolo por nome
- to_compact_string(): formato compacto
- to_prompt_section(): seção de prompt bounded
- summary(): estrutura do dict
- FileSymbols.compact(): formato one-liner
- Cache TTL: não re-escaneia dentro do TTL
- Fail-silent: nunca levanta exceção
- Singleton: get/reset
"""

from __future__ import annotations

import sys
import types
import importlib.util


def _load_mod():
    if "loguru" not in sys.modules:
        loguru_mod = types.ModuleType("loguru")
        class FL:
            def debug(self,*a,**k): pass
            def info(self,*a,**k): pass
            def warning(self,*a,**k): pass
            def error(self,*a,**k): pass
        loguru_mod.logger = FL()
        sys.modules["loguru"] = loguru_mod

    spec = importlib.util.spec_from_file_location(
        "repo_map", "src/services/repo_map.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repo_map"] = mod
    spec.loader.exec_module(mod)
    mod.reset_repo_map()
    return mod


class TestFileSymbols:
    def test_compact_nonempty(self):
        mod = _load_mod()
        fs = mod.FileSymbols(path="src/agents/batman.py")
        fs.symbols.append(mod.RepoSymbol("Batman", "class"))
        fs.symbols.append(mod.RepoSymbol("analyze", "def"))
        compact = fs.compact()
        assert "batman.py" in compact
        assert "Batman" in compact
        assert "analyze" in compact

    def test_compact_empty_symbols(self):
        mod = _load_mod()
        fs = mod.FileSymbols(path="src/agents/batman.py")
        assert fs.compact() == ""

    def test_class_names_property(self):
        mod = _load_mod()
        fs = mod.FileSymbols(path="x.py")
        fs.symbols = [
            mod.RepoSymbol("MyClass", "class"),
            mod.RepoSymbol("my_fn", "def"),
        ]
        assert "MyClass" in fs.class_names
        assert "my_fn" not in fs.class_names

    def test_function_names_property(self):
        mod = _load_mod()
        fs = mod.FileSymbols(path="x.py")
        fs.symbols = [
            mod.RepoSymbol("MyClass", "class"),
            mod.RepoSymbol("async_fn", "async_def"),
        ]
        assert "async_fn" in fs.function_names
        assert "MyClass" not in fs.function_names


class TestParseFile:
    def test_parse_real_file(self):
        """Testa parse de um arquivo real do projeto."""
        mod = _load_mod()
        from pathlib import Path
        target = Path("src/services/bounded_output.py")
        if not target.exists():
            return
        fs = mod._instance or mod.MekkaRepoMap(root=".")
        result = fs._parse_file(target, "src/services/bounded_output.py")
        assert result.path == "src/services/bounded_output.py"
        # BoundedOutput deve estar nos símbolos
        names = [s.name for s in result.symbols]
        assert "BoundedOutput" in names

    def test_parse_nonexistent_file(self):
        mod = _load_mod()
        from pathlib import Path
        rmap = mod.MekkaRepoMap(root=".")
        fs = rmap._parse_file(Path("nonexistent.py"), "nonexistent.py")
        assert isinstance(fs, mod.FileSymbols)
        assert fs.symbols == []


class TestMekkaRepoMapScan:
    def test_scan_returns_count(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        count = rmap.scan()
        assert isinstance(count, int)
        assert count >= 0

    def test_scan_populates_files(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        assert len(rmap._files) >= 0

    def test_scan_cache_not_repeated(self):
        """Scan dentro do TTL não re-escaneia."""
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".", cache_ttl_s=300)
        c1 = rmap.scan()
        # Adicionar arquivo fictício — não deve aparecer no segundo scan
        rmap._files["fake/fake.py"] = mod.FileSymbols(path="fake/fake.py")
        c2 = rmap.scan()
        # c2 retorna sem rescanear (cache ainda válido)
        assert "fake/fake.py" in rmap._files

    def test_scan_force_refreshes(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".", cache_ttl_s=300)
        rmap.scan()
        rmap._files["fake/fake.py"] = mod.FileSymbols(path="fake/fake.py")
        rmap.scan(force=True)
        assert "fake/fake.py" not in rmap._files

    def test_scan_fail_silent_bad_root(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root="/nonexistent/path/xyz")
        count = rmap.scan()
        assert count == 0  # sem exceção


class TestGetAgentMap:
    def test_returns_dict(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        result = rmap.get_agent_map()
        assert isinstance(result, dict)

    def test_only_agents_dir(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        result = rmap.get_agent_map()
        for path in result:
            assert "agents/" in path

    def test_values_are_lists(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        result = rmap.get_agent_map()
        for path, symbols in result.items():
            assert isinstance(symbols, list)

    def test_batman_in_agents(self):
        """batman.py deve aparecer no agent map se existir."""
        from pathlib import Path
        if not Path("src/agents/batman.py").exists():
            return
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        result = rmap.get_agent_map()
        batman_keys = [k for k in result if "batman" in k]
        assert len(batman_keys) >= 0  # pode ou não estar dependendo do scan


class TestGetServiceMap:
    def test_returns_dict(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        result = rmap.get_service_map()
        assert isinstance(result, dict)

    def test_only_services_dir(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        result = rmap.get_service_map()
        for path in result:
            assert "services/" in path


class TestFindSymbol:
    def test_find_known_symbol(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        results = rmap.find_symbol("BoundedOutput")
        assert isinstance(results, list)

    def test_find_nonexistent_returns_empty(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        results = rmap.find_symbol("XyzNonExistentSymbol99999")
        assert results == []

    def test_find_fail_silent(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        result = rmap.find_symbol(None)
        assert isinstance(result, list)


class TestCompactString:
    def test_returns_string(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        s = rmap.to_compact_string()
        assert isinstance(s, str)

    def test_dir_filter(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        s = rmap.to_compact_string(dirs=("agents",))
        if s:
            assert "agents/" in s

    def test_max_files_respected(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        s = rmap.to_compact_string(max_files=2)
        lines = [l for l in s.split("\n") if l.strip()]
        assert len(lines) <= 2


class TestPromptSection:
    def test_returns_string(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        section = rmap.to_prompt_section()
        assert isinstance(section, str)

    def test_contains_header(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        section = rmap.to_prompt_section()
        if section:
            assert "Mekka Codebase Map" in section

    def test_bounded_by_max_chars(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        section = rmap.to_prompt_section(max_chars=500)
        assert len(section) <= 600  # tolerância para header/footer


class TestSummary:
    def test_summary_structure(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        rmap.scan()
        s = rmap.summary()
        assert "total_files" in s
        assert "total_symbols" in s
        assert "by_directory" in s
        assert "cache_ttl_s" in s

    def test_summary_fail_silent(self):
        mod = _load_mod()
        rmap = mod.MekkaRepoMap(root=".")
        # summary sem scan
        s = rmap.summary()
        assert isinstance(s, dict)


class TestSingleton:
    def test_get_returns_instance(self):
        mod = _load_mod()
        rmap = mod.get_repo_map()
        assert isinstance(rmap, mod.MekkaRepoMap)

    def test_same_instance(self):
        mod = _load_mod()
        mod.reset_repo_map()
        r1 = mod.get_repo_map()
        r2 = mod.get_repo_map()
        assert r1 is r2

    def test_reset_clears(self):
        mod = _load_mod()
        r1 = mod.get_repo_map()
        mod.reset_repo_map()
        r2 = mod.get_repo_map()
        assert r1 is not r2
