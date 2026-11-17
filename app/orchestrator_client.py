import aiohttp


class OrchestratorClient:
  def __init__(self, base_url: str, token: str):
    self.base_url = base_url.rstrip("/")
    self.token = token

  async def start_user(self, telegram_id: int, modules: list[str]) -> dict:
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
      async with session.post(
        f"{self.base_url}/users/{telegram_id}/start",
        json={"modules": modules},
        headers={"Authorization": f"Bearer {self.token}"},
      ) as response:
        payload = await response.json()
        if response.status >= 400:
          raise RuntimeError(payload.get("detail", "Worker start failed"))
        return payload

  async def user_status(self, telegram_id: int) -> dict:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
      async with session.get(
        f"{self.base_url}/users/{telegram_id}/status",
        headers={"Authorization": f"Bearer {self.token}"},
      ) as response:
        payload = await response.json()
        if response.status >= 400:
          raise RuntimeError(payload.get("detail", "Worker status failed"))
        return payload
