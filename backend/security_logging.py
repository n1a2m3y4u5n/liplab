"""접근 로그에는 IP·URL(자유 입력 쿼리 포함)을 남기지 않는다."""
import logging


class AccessPrivacyFilter(logging.Filter):
    def filter(self, record):
        # Uvicorn access formatter의 표준 인자: client, method, target, version, status.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            _, method, _, version, status = record.args
            record.args = ("[client]", method, "[request]", version, status)
        else:
            # 알 수 없는 formatter에서도 주소·요청 원문이 빠져나가지 않게 한다.
            record.msg, record.args = "access request", ()
        return True


class ExceptionPrivacyFilter(logging.Filter):
    def filter(self, record):
        # 프레임워크가 다시 로깅하는 예외에도 DB 매개변수·응답 본문이 있을 수 있다.
        if record.exc_info:
            record.msg = "ASGI error: %s"
            record.args = (record.exc_info[0].__name__,)
            record.exc_info = record.exc_text = None
        return True


def install():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessPrivacyFilter) for f in logger.filters):
        logger.addFilter(AccessPrivacyFilter())
    errors = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, ExceptionPrivacyFilter) for f in errors.filters):
        errors.addFilter(ExceptionPrivacyFilter())
