import time
import logging
from fastapi import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")


async def logging_middleware(request: Request, call_next):
	start_time = time.time()

	response = await call_next(request)

	process_time = (time.time() - start_time) * 1000

	logger.info(
		f"{request.method} {request.url.path} "
		f"{response.status_code} "
		f"{process_time:.2f}ms"
	)

	return response