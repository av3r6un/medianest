from aiohttp.web import RouteTableDef


health = RouteTableDef()


@health.get('/health')
async def get_health(req, session=None):
  from backend import settings

  return settings.api_info
