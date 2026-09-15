from eventserver.api.schemas import PermissionResponse, PermissionValues
from eventserver.services.users import PermissionSnapshot


def permission_response(snapshot: PermissionSnapshot) -> PermissionResponse:
    return PermissionResponse(
        platform=snapshot.platform,
        openid=snapshot.openid,
        account_status=snapshot.account_status,
        role=snapshot.role,
        permissions=PermissionValues(chat=snapshot.chat, command=snapshot.command),
    )
