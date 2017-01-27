# -*- mode: python -*-

# Taken from: https://github.com/pyinstaller/pyinstaller/wiki/Recipe-Setuptools-Entry-Point
def Entrypoint(dist, group, name, datas=None,
               scripts=None, pathex=None, hiddenimports=None,
               hookspath=None, excludes=None, runtime_hooks=None):
    import pkg_resources

    # get toplevel packages of distribution from metadata
    def get_toplevel(dist):
        distribution = pkg_resources.get_distribution(dist)
        if distribution.has_metadata('top_level.txt'):
            return list(distribution.get_metadata('top_level.txt').split())
        else:
            return []

    hiddenimports = hiddenimports or []
    packages = []
    for distribution in hiddenimports:
        packages += get_toplevel(distribution)

    scripts = scripts or []
    pathex = pathex or []
    # get the entry point
    ep = pkg_resources.get_entry_info(dist, group, name)
    # insert path of the egg at the verify front of the search path
    pathex = [ep.dist.location] + pathex
    # script name must not be a valid module name to avoid name clashes on import
    script_path = os.path.join(workpath, name + '-script.py')
    print "creating script for entry point", dist, group, name
    with open(script_path, 'w') as fh:
        fh.write("import {0}\n".format(ep.module_name))
        fh.write("{0}.{1}()\n".format(ep.module_name, '.'.join(ep.attrs)))
        for package in packages:
            fh.write("import {0}\n".format(package))

    hiddenimports = [
        'ometa._generated.parsley',
        'ometa._generated.parsley_termactions',
        'ometa._generated.parsley_tree_transformer',
        'ometa._generated.pymeta_v1',
        'ometa._generated.vm',
        'ometa._generated.vm_emit',
        'terml._generated.terml',
        'terml._generated.quasiterm',
        'ooni.templates',
        'ooni.templates.dnst',
        'ooni.templates.httpt',
        'ooni.templates.process',
        'ooni.templates.scapyt',
        'ooni.templates.tcpt',
        'ooni.common',
        'ooni.common.http_utils',
        'ooni.common.ip_utils',
        'ooni.common.tcp_utils',
        'ooni.common.txextra'
    ]
    return Analysis([script_path] + scripts,
                    pathex=pathex,
                    datas=datas,
                    hiddenimports=hiddenimports,
                    hookspath=hookspath,
                    excludes=excludes,
                    runtime_hooks=runtime_hooks)

block_cipher = None

#hiddenimports = ['parsley']

datas = [
    ('ooni/nettests/blocking/*.py', 'ooni/nettests/blocking'),
    ('ooni/nettests/manipulation/*.py', 'ooni/nettests/manipulation'),
    ('ooni/nettests/experimental/*.py', 'ooni/nettests/experimental'),
    ('ooni/nettests/third_party/*.py', 'ooni/nettests/third_party')
]
a = Entrypoint('ooniprobe',
               'console_scripts',
               'ooniprobe-agent',
               datas=datas)

a = Entrypoint('ooniprobe',
               'console_scripts',
               'ooniprobe', datas=datas)

pyz = PYZ(a.pure, a.zipped_data,
          cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='ooniprobe_agent',
          debug=False,
          strip=False,
          upx=True,
          console=True )
