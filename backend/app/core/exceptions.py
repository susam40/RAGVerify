class AppError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class FetchError(AppError):
    pass


class ExtractError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)
