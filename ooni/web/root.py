import os
import re
import json
from twisted.web import resource, static


class WuiResource(resource.Resource):
    isLeaf = True
    def __init__(self, director):
        self.director = director
        resource.Resource.__init__(self)

    def render(self, request):
        obj = resource.Resource.render(self, request)
        return self.render_json(obj, request)

    def render_json(self, obj, request):
        json_string = json.dumps(obj) + "\n"
        request.setHeader('Content-Type', 'application/json')
        request.setHeader('Content-Length', len(json_string))
        return json_string


class DeckGenerate(WuiResource):
    def render_GET(self, request):
        return {"generate": "deck"}


class DeckStart(WuiResource):
    def __init__(self, director, deck_name):
        WuiResource.__init__(self, director)
        self.deck_name = deck_name

    def render_GET(self, request):
        return {"start": self.deck_name}


class DeckStatus(WuiResource):
    def __init__(self, director, deck_name):
        WuiResource.__init__(self, director)
        self.deck_name = deck_name

    def render_GET(self, request):
        return {"deck": self.deck_name}


class DeckList(WuiResource):
    def render_GET(self, request):
        return {"deck": "list"}


class Results(WuiResource):
    def render_GET(self, request):
        return {"result": "bar"}


class OONIProbeWebRoot(resource.Resource):
    routes = [
        ('^/deck/generate$', DeckGenerate),
        ('^/deck/(.*)/start$', DeckStart),
        ('^/deck/(.*)$', DeckStatus),
        ('^/deck$', DeckList),
        ('^/results$', Results)
    ]
    def __init__(self, config, director):
        resource.Resource.__init__(self)

        self._director = director
        self._config = config
        self._route_map = map(lambda x: (re.compile(x[0]), x[1]), self.routes)

        wui_directory = os.path.join(self._config.data_directory, 'ui', 'app')
        self._static = static.File(wui_directory)


    def getChild(self, path, request):
        for route, r in self._route_map:
            match = route.search(request.path)
            if match:
                return r(self._director, *match.groups())
        return self._static.getChild(path, request)
