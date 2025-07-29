from rest_framework import status
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.utils import timezone
from typing import Dict, Any, Optional, List
import structlog

logger = structlog.get_logger(__name__)


class BaseAPIException(Exception):
    """
    Base exception class for all API exceptions
    Provides consistent error structure and logging
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'An error occurred'
    default_code = 'error'
    category = 'general'

    def __init__(self, detail: str = None, code: str = None, extra_data: Dict[str, Any] = None):
        self.detail = detail or self.default_detail
        self.code = code or self.default_code
        self.extra_data = extra_data or {}
        self.timestamp = timezone.now()

        # Log the exception
        self.log_exception()

        super().__init__(self.detail)

    def log_exception(self):
        """Log the exception with structured data"""
        logger.error(
            f"{self.__class__.__name__} raised",
            detail=self.detail,
            code=self.code,
            status_code=self.status_code,
            category=self.category,
            extra_data=self.extra_data,
            timestamp=self.timestamp.isoformat(),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API response"""
        return {
            'error': self.code,
            'message': self.detail,
            'status_code': self.status_code,
            'category': self.category,
            'timestamp': self.timestamp.isoformat(),
            **self.extra_data
        }


class ValidationError(BaseAPIException):
    """
    Validation error for input data
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Invalid input data'
    default_code = 'validation_error'
    category = 'validation'

    def __init__(self, detail: str = None, field_errors: Dict[str, List[str]] = None, **kwargs):
        self.field_errors = field_errors or {}
        super().__init__(detail, **kwargs)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        if self.field_errors:
            data['field_errors'] = self.field_errors
        return data


class AuthenticationError(BaseAPIException):
    """
    Authentication related errors
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Authentication required'
    default_code = 'authentication_error'
    category = 'authentication'


class PermissionError(BaseAPIException):
    """
    Permission/authorization related errors
    """

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Permission denied'
    default_code = 'permission_error'
    category = 'authorization'


class NotFoundError(BaseAPIException):
    """
    Resource not found errors
    """

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = 'Resource not found'
    default_code = 'not_found'
    category = 'resource'


class ConflictError(BaseAPIException):
    """
    Resource conflict errors
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Resource conflict'
    default_code = 'conflict_error'
    category = 'resource'


class RateLimitExceededError(BaseAPIException):
    """
    Rate limiting errors
    """

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = 'Rate limit exceeded'
    default_code = 'rate_limit_exceeded'
    category = 'rate_limiting'

    def __init__(self, detail: str = None, retry_after: int = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(detail, **kwargs)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        if self.retry_after:
            data['retry_after'] = self.retry_after
        return data


class ServiceUnavailableError(BaseAPIException):
    """
    Service unavailable errors
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'Service temporarily unavailable'
    default_code = 'service_unavailable'
    category = 'service'


class ExternalServiceError(BaseAPIException):
    """
    External service integration errors
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'External service error'
    default_code = 'external_service_error'
    category = 'integration'

    def __init__(self, detail: str = None, service_name: str = None, **kwargs):
        self.service_name = service_name
        super().__init__(detail, **kwargs)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        if self.service_name:
            data['service'] = self.service_name
        return data


class SecurityError(BaseAPIException):
    """
    Security related errors
    """

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Security violation detected'
    default_code = 'security_error'
    category = 'security'

    def log_exception(self):
        """Enhanced logging for security errors"""
        logger.error(
            f"SECURITY ALERT: {self.__class__.__name__}",
            detail=self.detail,
            code=self.code,
            status_code=self.status_code,
            category=self.category,
            extra_data=self.extra_data,
            timestamp=self.timestamp.isoformat(),
            alert_level='HIGH',
        )


# FPL-specific exceptions

class FPLAPIError(ExternalServiceError):
    """
    Fantasy Premier League API errors
    """

    default_detail = 'FPL API error'
    default_code = 'fpl_api_error'

    def __init__(self, detail: str = None, **kwargs):
        super().__init__(detail, service_name='FPL API', **kwargs)


class PlayerNotFoundError(NotFoundError):
    """
    Player not found in database
    """

    default_detail = 'Player not found'
    default_code = 'player_not_found'

    def __init__(self, player_id: int = None, **kwargs):
        detail = f"Player with ID {player_id} not found" if player_id else kwargs.get('detail')
        super().__init__(detail, extra_data={'player_id': player_id} if player_id else None, **kwargs)


class TeamNotFoundError(NotFoundError):
    """
    Team not found in FPL system
    """

    default_detail = 'FPL team not found'
    default_code = 'team_not_found'

    def __init__(self, team_id: int = None, **kwargs):
        detail = f"FPL team with ID {team_id} not found" if team_id else kwargs.get('detail')
        super().__init__(detail, extra_data={'team_id': team_id} if team_id else None, **kwargs)


class InvalidTeamStructureError(ValidationError):
    """
    Invalid team structure (formation, budget, etc.)
    """

    default_detail = 'Invalid team structure'
    default_code = 'invalid_team_structure'


class BudgetExceededError(ValidationError):
    """
    Team budget exceeded error
    """

    default_detail = 'Team budget exceeded'
    default_code = 'budget_exceeded'

    def __init__(self, current_value: float = None, budget_limit: float = None, **kwargs):
        detail = kwargs.get('detail')
        if not detail and current_value and budget_limit:
            detail = f"Team value £{current_value}m exceeds budget limit of £{budget_limit}m"

        super().__init__(
            detail,
            extra_data={
                'current_value': current_value,
                'budget_limit': budget_limit
            } if current_value and budget_limit else None,
            **kwargs
        )


class TransferLimitExceededError(ValidationError):
    """
    Transfer limit exceeded error
    """

    default_detail = 'Transfer limit exceeded'
    default_code = 'transfer_limit_exceeded'


class DataSyncError(BaseAPIException):
    """
    Data synchronization errors
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'Data synchronization failed'
    default_code = 'data_sync_error'
    category = 'data_sync'


class CacheError(BaseAPIException):
    """
    Cache related errors
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'Cache service error'
    default_code = 'cache_error'
    category = 'cache'


class AsyncTaskError(BaseAPIException):
    """
    Asynchronous task errors
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'Async task failed'
    default_code = 'async_task_error'
    category = 'async'

    def __init__(self, detail: str = None, task_id: str = None, **kwargs):
        self.task_id = task_id
        super().__init__(detail, **kwargs)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        if self.task_id:
            data['task_id'] = self.task_id
        return data


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF
    Provides consistent error responses across the API
    """
    request = context.get('request')
    request_id = getattr(request, 'id', 'unknown') if request else 'unknown'

    # Handle our custom exceptions
    if isinstance(exc, BaseAPIException):
        response_data = exc.to_dict()
        response_data['request_id'] = request_id

        # Add retry-after header for rate limiting
        response = Response(response_data, status=exc.status_code)
        if isinstance(exc, RateLimitExceededError) and exc.retry_after:
            response['Retry-After'] = str(exc.retry_after)

        return response

    # Handle Django validation errors
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, 'message_dict'):
            # Field-specific validation errors
            field_errors = {}
            for field, messages in exc.message_dict.items():
                field_errors[field] = messages

            validation_error = ValidationError(
                detail='Validation failed',
                field_errors=field_errors
            )
            response_data = validation_error.to_dict()
        else:
            # Non-field validation errors
            validation_error = ValidationError(detail=str(exc))
            response_data = validation_error.to_dict()

        response_data['request_id'] = request_id
        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    # Let DRF handle other exceptions
    response = drf_exception_handler(exc, context)

    if response is not None:
        # Enhance DRF error responses
        if isinstance(response.data, dict):
            response.data['request_id'] = request_id
            response.data['timestamp'] = timezone.now().isoformat()

            # Convert DRF error format to our format
            if 'detail' in response.data:
                error_detail = response.data.pop('detail')
                response.data['message'] = str(error_detail)
                response.data['error'] = 'api_error'

        # Log the exception
        logger.error(
            "DRF exception handled",
            exception=str(exc),
            exception_type=exc.__class__.__name__,
            status_code=response.status_code,
            request_id=request_id,
            path=request.path if request else None,
            method=request.method if request else None,
        )

    return response


class ExceptionContext:
    """
    Context manager for exception handling with additional data
    """

    def __init__(self, operation: str, **context_data):
        self.operation = operation
        self.context_data = context_data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type and issubclass(exc_type, BaseAPIException):
            # Add context data to the exception
            exc_value.extra_data.update({
                'operation': self.operation,
                **self.context_data
            })

        return False  # Don't suppress the exception


# Utility functions for error handling

def handle_external_service_error(service_name: str, original_exception: Exception) -> ExternalServiceError:
    """
    Convert external service exceptions to our format
    """
    detail = f"{service_name} service error: {str(original_exception)}"
    return ExternalServiceError(
        detail=detail,
        service_name=service_name,
        extra_data={'original_error': str(original_exception)}
    )


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> None:
    """
    Validate that required fields are present in data
    """
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]

    if missing_fields:
        field_errors = {field: ['This field is required.'] for field in missing_fields}
        raise ValidationError(
            detail=f"Missing required fields: {', '.join(missing_fields)}",
            field_errors=field_errors
        )


def validate_field_types(data: Dict[str, Any], field_types: Dict[str, type]) -> None:
    """
    Validate field types in data
    """
    field_errors = {}

    for field, expected_type in field_types.items():
        if field in data and data[field] is not None:
            if not isinstance(data[field], expected_type):
                field_errors[field] = [f'Expected {expected_type.__name__}, got {type(data[field]).__name__}']

    if field_errors:
        raise ValidationError(
            detail='Invalid field types',
            field_errors=field_errors
        )


def validate_numeric_range(value: float, min_value: float = None,
                          max_value: float = None, field_name: str = 'value') -> None:
    """
    Validate numeric value is within range
    """
    errors = []

    if min_value is not None and value < min_value:
        errors.append(f'Value must be at least {min_value}')

    if max_value is not None and value > max_value:
        errors.append(f'Value must be at most {max_value}')

    if errors:
        raise ValidationError(
            detail=f'Invalid {field_name}',
            field_errors={field_name: errors}
        )


def safe_execute(func, *args, default_return=None, exception_class=BaseAPIException, **kwargs):
    """
    Safely execute a function and handle exceptions
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if isinstance(e, BaseAPIException):
            raise

        # Convert to our exception format
        raise exception_class(
            detail=f"Operation failed: {str(e)}",
            extra_data={'original_error': str(e)}
        )


# Error code registry for consistent error handling
ERROR_CODES = {
    # General errors
    'VALIDATION_ERROR': 'validation_error',
    'AUTHENTICATION_ERROR': 'authentication_error',
    'PERMISSION_ERROR': 'permission_error',
    'NOT_FOUND': 'not_found',
    'CONFLICT': 'conflict_error',
    'RATE_LIMIT_EXCEEDED': 'rate_limit_exceeded',
    'SERVICE_UNAVAILABLE': 'service_unavailable',

    # FPL specific errors
    'FPL_API_ERROR': 'fpl_api_error',
    'PLAYER_NOT_FOUND': 'player_not_found',
    'TEAM_NOT_FOUND': 'team_not_found',
    'INVALID_TEAM_STRUCTURE': 'invalid_team_structure',
    'BUDGET_EXCEEDED': 'budget_exceeded',
    'TRANSFER_LIMIT_EXCEEDED': 'transfer_limit_exceeded',

    # System errors
    'DATA_SYNC_ERROR': 'data_sync_error',
    'CACHE_ERROR': 'cache_error',
    'ASYNC_TASK_ERROR': 'async_task_error',
    'SECURITY_ERROR': 'security_error',
}


def get_error_code(error_type: str) -> str:
    """
    Get standardized error code for error type
    """
    return ERROR_CODES.get(error_type.upper(), 'unknown_error')
