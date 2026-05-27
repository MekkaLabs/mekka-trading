"""
src/dashboard/handlers/
========================
Submódulos de handlers por domínio, extraídos de server.py.

PADRÃO
------
Cada módulo (ex.: system.py, trade.py) expõe funções com a assinatura:

    async def handler_fn(server: "MekkaDashboardServer", request: web.Request) -> web.Response

O server.py atua como mediador — registra rotas apontando para essas
funções via `lambda req: handler(self, req)` ou métodos de instância
delegantes. Isso preserva o acoplamento mínimo necessário (acesso a
`server._runtime`, `server._cache`, etc.) sem manter os handlers
inflados no arquivo principal.

REFATORAÇÃO
-----------
IMP-7cf025b8f64d (P1 HIGH) — server.py original tinha 6951 linhas, 251
handlers, dificultando navegação e manutenção. A extração é incremental:
cada PR move um grupo de handlers do mesmo domínio. Comportamento
preservado byte-a-byte — apenas mudança de localização.
"""
