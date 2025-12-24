I am trying to run backend and it crashes. Diagnose, and renove code if we don't need it. We do not need to migrate data in this development enviroment, 

carashes: 

ero.api.main:app --port 8765
Migration check failed: Catalog Error: Table with name workflows does not exist!
Did you mean "duckdb_logs"?

LINE 1: SELECT * FROM pragma_table_info('workflows');
                      ^
Migration check failed: Catalog Error: Table with name workflows does not exist!
Did you mean "duckdb_logs"?

LINE 1: SELECT * FROM pragma_table_info('workflows');
                      ^
Form data requires "python-multipart" to be installed. 
You can install "python-multipart" with: 

pip install python-multipart

Traceback (most recent call last):
  File "/Users/dtubb/code/fichero_main/fichero/.venv/bin/uvicorn", line 7, in <module>
    sys.exit(main())
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/click/core.py", line 1485, in __call__
    return self.main(*args, **kwargs)
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/click/core.py", line 1406, in main
    rv = self.invoke(ctx)
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/click/core.py", line 1269, in invoke
    return ctx.invoke(self.callback, **ctx.params)
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/click/core.py", line 824, in invoke
    return callback(*args, **kwargs)
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/uvicorn/main.py", line 423, in main
    run(
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/uvicorn/main.py", line 593, in run
    server.run()
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/uvicorn/server.py", line 67, in run
    return asyncio_run(self.serve(sockets=sockets), loop_factory=self.config.get_loop_factory())
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/uvicorn/_compat.py", line 60, in asyncio_run
    return loop.run_until_complete(main)
  File "/Users/dtubb/miniforge3/lib/python3.10/asyncio/base_events.py", line 649, in run_until_complete
    return future.result()
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/uvicorn/server.py", line 71, in serve
    await self._serve(sockets)
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/uvicorn/server.py", line 78, in _serve
    config.load()
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/uvicorn/config.py", line 439, in load
    self.loaded_app = import_from_string(self.app)
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/uvicorn/importer.py", line 19, in import_from_string
    module = importlib.import_module(module_str)
  File "/Users/dtubb/miniforge3/lib/python3.10/importlib/__init__.py", line 126, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
  File "<frozen importlib._bootstrap>", line 1050, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1027, in _find_and_load
  File "<frozen importlib._bootstrap>", line 992, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "<frozen importlib._bootstrap>", line 1050, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1027, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1006, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 688, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 883, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/dtubb/code/fichero_main/fichero/src/fichero/api/__init__.py", line 17, in <module>
    from fichero.api.main import app
  File "/Users/dtubb/code/fichero_main/fichero/src/fichero/api/main.py", line 88, in <module>
    from fichero.api.routes import documents, search, ingest, storage, chat, providers, workflows, models
  File "/Users/dtubb/code/fichero_main/fichero/src/fichero/api/routes/documents.py", line 208, in <module>
    async def import_file(
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 1128, in decorator
    self.add_api_route(
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 1067, in add_api_route
    route = route_class(
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 686, in __init__
    self.dependant = get_dependant(
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/fastapi/dependencies/utils.py", line 288, in get_dependant
    param_details = analyze_param(
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/fastapi/dependencies/utils.py", line 525, in analyze_param
    ensure_multipart_is_installed()
  File "/Users/dtubb/code/fichero_main/fichero/.venv/lib/python3.10/site-packages/fastapi/dependencies/utils.py", line 121, in ensure_multipart_is_installed
    raise RuntimeError(multipart_not_installed_error) from None
RuntimeError: Form data requires "python-multipart" to be installed. 
You can install "python-multipart" with: 

pip install python-multipart

(.venv) (base) dtubb@UNB-C02F45GAQ05P fichero % 