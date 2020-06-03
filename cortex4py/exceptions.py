class CortexException(Exception):
    pass


class NotFoundError(CortexException):
    pass


class AuthenticationError(CortexException):
    pass


class AuthorizationError(CortexException):
    pass


class InvalidInputError(CortexException):
    pass


class ServiceUnavailableError(CortexException):
    pass


class ServerError(CortexException):
    pass


class CortexError(CortexException):
    pass