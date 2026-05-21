"""HTTP route handler modules extracted from the monolithic dashboard server.

Each module exposes plain ``async def handle_*(server, request)`` functions that
operate on the ``MekkaDashboardServer`` instance passed in. server.py keeps the
route registration (so wiring is unchanged) and delegates the body here — this
shrinks server.py without changing behaviour.
"""
