from aiohttp.web import RouteTableDef


config = RouteTableDef()


@config.get('/config/diagnostics')
async def config_diagnostics(req, session=None):
  from backend import settings

  return settings.diagnostics
