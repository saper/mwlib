#! /usr/bin/env python

# Copyright (c) 2007-2009 PediaPress GmbH
# See README.txt for additional licensing information.

import os
from ConfigParser import ConfigParser
import StringIO

from mwlib.log import Log
from mwlib import myjson

log = Log('mwlib.utils')

class dummy_web_wiki(object):
    def __init__(self,  **kw):
        self.__dict__.update(**kw)
        
def wiki_zip(path=None, url=None, name=None, **kwargs):
    from mwlib import zipwiki
    if kwargs:
        log.warn('Unused parameters: %r' % kwargs)
    return zipwiki.Wiki(path)


def wiki_obsolete_cdb(path=None,  **kwargs):
    raise RuntimeError("cdb file format has changed. please rebuild with mw-buildcdb")

def wiki_nucdb(path=None, lang="en", **kwargs):
    from mwlib import cdbwiki,  nuwiki
    path = os.path.expanduser(path)
    db=cdbwiki.WikiDB(path, lang=lang)
    return nuwiki.adapt(db)

def image_zip(path=None, **kwargs):
    from mwlib import zipwiki
    if kwargs:
        log.warn('Unused parameters: %r' % kwargs)
    return zipwiki.ImageDB(path)



dispatch = dict(
    images = dict(zip=image_zip),
    wiki = dict(cdb=wiki_obsolete_cdb, nucdb=wiki_nucdb, zip=wiki_zip)
)

_en_license_url = 'http://en.wikipedia.org/w/index.php?title=Wikipedia:Text_of_the_GNU_Free_Documentation_License&action=raw'
wpwikis = dict(
    de = dict(baseurl='http://de.wikipedia.org/w/', 
              mw_license_url='http://de.wikipedia.org/w/index.php?title=Hilfe:Buchfunktion/Lizenz&action=raw'),
    en = dict(baseurl='http://en.wikipedia.org/w/', mw_license_url=_en_license_url),
    fr = dict(baseurl='http://fr.wikipedia.org/w/', mw_license_url=None),
    es = dict(baseurl='http://es.wikipedia.org/w/', mw_license_url=None),
    pt = dict(baseurl='http://pt.wikipedia.org/w/', mw_license_url=None),
    enwb = dict(baseurl='http://en.wikibooks.org/w', mw_license_url=_en_license_url),
    commons = dict(baseurl='http://commons.wikimedia.org/w/', mw_license_url=_en_license_url)
    )


class Environment(object):
    def __init__(self, metabook=None):
        self.metabook = metabook
        self.images = None
        self.wiki = None
        self.configparser = ConfigParser()
        defaults=StringIO.StringIO("""
[wiki]
name=
url=
""")
        self.configparser.readfp(defaults)

    def _get_wiki(self):
        import warnings
        warnings.warn("access with .wiki deprecated", DeprecationWarning, 2)
        
        return self._wiki
    def _set_wiki(self, val):
        self._wiki = val

    wiki = property(_get_wiki, _set_wiki)
    
    def init_metabook(self):
        if self.metabook:
            self.metabook.set_environment(self)

    def getLicenses(self):
        return self.wiki.getLicenses()
    
class MultiEnvironment(Environment):
    wiki = None
    images = None
    
    def __init__(self, path):
        Environment.__init__(self)
        self.path = path
        self.metabook = myjson.load(open(os.path.join(self.path, "metabook.json")))
        self.id2env = {}
        
    def init_metabook(self):
        from mwlib import nuwiki
        if not self.metabook:
            return
        
        for x in self.metabook.articles():
            id = x.wikiident
            assert id, "article has no wikiident: %r" % (x,)
            assert "/" not in id
            assert ".." not in id
            
            if id not in self.id2env:
                env = Environment()
                env.images = env.wiki = nuwiki.adapt(os.path.join(self.path, id))
                self.id2env[id] = env
            else:
                env = self.id2env[id]
            x._env = env
            
    def getLicenses(self):
        res = []
        for x in self.id2env.values():
            tmp = x.wiki.getLicenses()
            for t in tmp:
                t._env = x
            res += tmp
        
        return res
            
            
        
def _makewiki(conf,
    metabook=None,
    username=None, password=None, domain=None,
    script_extension=None,
):
    res = Environment(metabook)
    
    url = None
    if conf.startswith(':'):
        if conf[1:] not in wpwikis:
            wpwikis[conf[1:]] =  dict(baseurl = "http://%s.wikipedia.org/w/" % conf[1:],
                                      mw_license_url =  None)
            

        url = wpwikis.get(conf[1:])['baseurl']

    if conf.startswith("http://") or conf.startswith("https://"):
        url = conf

    if url:
        res.wiki = dummy_web_wiki(url=url,
            username=username,
            password=password,
            domain=domain,
            script_extension=script_extension,
        )
        res.image = None
        
        return res

    if os.path.exists(os.path.join(conf, "siteinfo.json")):
        from mwlib import nuwiki
        res.images = res.wiki = nuwiki.adapt(conf)
        if metabook is None:
            res.metabook = res.wiki.metabook
        
        return res
    
    # yes, I really don't want to type this everytime
    wc = os.path.join(conf, "wikiconf.txt")
    if os.path.exists(wc):
        conf = wc 
        
    if conf.lower().endswith(".zip"):
        import zipfile
        from mwlib import myjson as json
        conf = os.path.abspath(conf)
        
        zf = zipfile.ZipFile(conf)
        try:
            format = json.loads(zf.read("nfo.json"))["format"]
        except KeyError:
            format = "zipwiki"
            
        if format=="nuwiki":
            from mwlib import nuwiki
            res.images = res.wiki = nuwiki.adapt(zf)
            if metabook is None:
                res.metabook = res.wiki.metabook
            return res
        elif format==u'multi-nuwiki':
            from mwlib import nuwiki
            import tempfile
            res.wiki = res.images = None
            tmpdir = tempfile.mkdtemp()
            nuwiki.extractall(zf, tmpdir)
            res = MultiEnvironment(tmpdir)
            return res
        elif format=="zipwiki":
            from mwlib import zipwiki
            res.wiki = zipwiki.Wiki(conf)
            res.images = zipwiki.ImageDB(conf)
            if metabook is None:
                res.metabook = res.wiki.metabook
            return res
        else:
            raise RuntimeError("unknown format %r" % (format,))
        
    

    cp = res.configparser
    
    if not cp.read(conf):
        raise RuntimeError("could not read config file %r" % (conf,))

        
    for s in ['images', 'wiki']:
        if not cp.has_section(s):
            continue
        
        args = dict(cp.items(s))
        if "type" not in args:
            raise RuntimeError("section %r does not have key 'type'" % s)
        t = args['type']
        del args['type']
        try:
            m = dispatch[s][t]
        except KeyError:
            raise RuntimeError("cannot handle type %r in section %r" % (t, s))

        setattr(res, s, m(**args))
    
    assert res.wiki is not None, '_makewiki should have set wiki attribute'
    return res

def makewiki(conf,
    metabook=None,
    username=None, password=None, domain=None,
    script_extension=None,
):
    res = _makewiki(conf, metabook,
        username=username,
        password=password,
        domain=domain,
        script_extension=script_extension,
    )
    if res.wiki:
        res.wiki.env = res
    if res.images:
        res.images.env = res

    res.init_metabook()
    
    return res
