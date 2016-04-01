import os
import json
from twisted.web import resource
from twisted.web.static import File


class WuiResource(resource.Resource):
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


class Deck(WuiResource):
    pass


class Results(WuiResource):
    pass


class OONIProbeWebRoot(resource.Resource):
    def __init__(self, config, director):
        resource.Resource.__init__(self)
        wui_directory = os.path.join(config.data_directory, 'ui', 'app')
        # XXX figure out how to avoid having the extra / in the URL
        self.putChild('', File(wui_directory))
        # XXX figure out a better way to manage routing such as /deck/(.*)/start
        self.putChild('deck', Deck(director))
        self.putChild('results', Results(director))
