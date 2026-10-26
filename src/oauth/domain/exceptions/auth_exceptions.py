class AuthDomainException(Exception):
    """Excepción base para errores de dominio en el módulo OAuth."""
    pass


class InvalidCredentialsException(AuthDomainException):
    def __init__(self, message: str = "Credenciales inválidas (usuario o contraseña incorrectos)."):
        super().__init__(message)


class UserInactiveException(AuthDomainException):
    def __init__(self, message: str = "La cuenta de usuario está desactivada o cancelada."):
        super().__init__(message)


class UserEmailNotConfirmedException(AuthDomainException):
    def __init__(self, message: str = "El correo electrónico del usuario aún no ha sido confirmado."):
        super().__init__(message)


class IncompleteProfileException(AuthDomainException):
    def __init__(self, message: str = "El usuario debe completar su perfil (teléfono verificado y género) para operar."):
        super().__init__(message)


class InvalidClientException(AuthDomainException):
    def __init__(self, message: str = "Cliente OAuth no registrado o no válido."):
        super().__init__(message)


class InvalidRedirectUriException(AuthDomainException):
    def __init__(self, message: str = "La redirect_uri no coincide con las registradas para este cliente."):
        super().__init__(message)


class InvalidPKCEException(AuthDomainException):
    def __init__(self, message: str = "El code_verifier no supera el desafío code_challenge (PKCE S256 inválido)."):
        super().__init__(message)


class ExpiredAuthorizationCodeException(AuthDomainException):
    def __init__(self, message: str = "El código de autorización ha expirado o ya fue utilizado."):
        super().__init__(message)


class InvalidRefreshTokenException(AuthDomainException):
    def __init__(self, message: str = "El refresh token es inválido o ha sido revocado."):
        super().__init__(message)
