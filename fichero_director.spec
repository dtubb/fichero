# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['fichero_director.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Celery core & fixups
        'celery.fixups',
        'celery.fixups.django',
        'celery.backends',
        'celery.backends.base',
        'celery.loaders',
        'celery.loaders.app',
        'celery.app.amqp',
        'celery.app.events',
        'celery',
        
        'kombu.transport.redis',

        # Kombu (used by Celery)
        'kombu.transport',
        'kombu.async',

        # Redis (used as Celery broker)
        'redis',
        'kombu.transport.redis',
        'celery.backends.redis',

        # Typing/runtime plugins for langchain etc
        'langchain',
        'langchain.chains',
        'langchain.embeddings',
        'langchain.vectorstores',

        # Needed for some PyTorch models to avoid runtime import failures
        'torch',
        'transformers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='fichero_director',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='fichero_director',
)