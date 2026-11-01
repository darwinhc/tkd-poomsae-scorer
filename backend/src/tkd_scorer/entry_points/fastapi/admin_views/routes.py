import base64
from io import BytesIO
from urllib.parse import quote_plus

import qrcode
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from tkd_scorer.domain.exceptions.errors import DomainError
from tkd_scorer.infra.fastapi.admin_auth import (
    build_admin_auth_token,
    clear_login_failures,
    get_login_lock_seconds_remaining,
    is_admin_auth_enabled,
    is_admin_authenticated,
    normalize_next_path,
    register_login_failure,
)
from tkd_scorer.infra.fastapi.dependencies import AdminUseCases, get_admin_use_cases
from tkd_scorer.infra.i18n import translate

router = APIRouter()


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _t(request: Request, key: str, **params: object) -> str:
    return translate(key, request.app.state.settings.ui_language, **params)


def _qr_base64(payload: str) -> str:
    image = qrcode.make(payload)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _build_station_detail_context(
    *,
    request: Request,
    use_cases: AdminUseCases,
    station_id: str,
    reveal: bool,
    start_error: str | None = None,
    control_error: str | None = None,
    draw_preview: object | None = None,
    form_data: dict | None = None,
) -> dict:
    view = use_cases.views.station_detail(station_id, reveal_credential=reveal)
    match_view = use_cases.views.station_scoreboard(station_id)
    live_refresh_seconds = request.app.state.settings.admin_live_refresh_seconds
    live = use_cases.views.station_live_snapshot(
        station_id=station_id,
        rotate_credential=False,
        actor="admin-view",
        reveal_credential=reveal,
    )
    active_refresh_seconds = max(1, request.app.state.settings.admin_live_refresh_seconds // 4)
    return {
        "view": view,
        "match_view": match_view,
        "active_match": use_cases.views.active_match(station_id),
        "active_refresh_seconds": active_refresh_seconds,
        "control_error": control_error,
        "reveal": reveal,
        "live_refresh_seconds": live_refresh_seconds,
        "live": live,
        "station_qr_base64": _qr_base64(live.bootstrap_payload_json),
        "start_error": start_error,
        "draw_preview": draw_preview,
        "form_data": form_data,
    }


def _build_active_match_context(
    *,
    request: Request,
    use_cases: AdminUseCases,
    station_id: str,
    control_error: str | None = None,
) -> dict:
    station_view = use_cases.views.station_detail(station_id, reveal_credential=False)
    refresh_seconds = max(1, request.app.state.settings.admin_live_refresh_seconds // 4)
    return {
        "station": station_view,
        "active_match": use_cases.views.active_match(station_id),
        "refresh_seconds": refresh_seconds,
        "control_error": control_error,
    }


@router.get("/admin/login")
def admin_login_page(
    request: Request,
    next: str | None = None,
):
    settings = request.app.state.settings
    next_path = normalize_next_path(next_value=next, configured_base_path=settings.admin_base_path)
    if not is_admin_auth_enabled(request):
        return RedirectResponse(url=next_path, status_code=303)
    if is_admin_authenticated(request):
        return RedirectResponse(url=next_path, status_code=303)
    lock_seconds = get_login_lock_seconds_remaining(request)
    error = None
    if lock_seconds > 0:
        error = _t(request, "login.error_locked_retry", seconds=lock_seconds)
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/login.html",
        context={
            "next_path": next_path,
            "error": error,
            "hide_admin_chrome": True,
        },
    )


@router.post("/admin/login")
def admin_login_submit(
    request: Request,
    password: str = Form(""),
    next: str | None = Form(None),
):
    settings = request.app.state.settings
    next_path = normalize_next_path(next_value=next, configured_base_path=settings.admin_base_path)
    if not is_admin_auth_enabled(request):
        return RedirectResponse(url=next_path, status_code=303)

    locked_for_seconds = get_login_lock_seconds_remaining(request)
    if locked_for_seconds > 0:
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/login.html",
            context={
                "next_path": next_path,
                "error": _t(request, "login.error_locked_retry", seconds=locked_for_seconds),
                "hide_admin_chrome": True,
            },
            status_code=429,
        )

    if password != settings.admin_password:
        failure_result = register_login_failure(
            request,
            max_attempts=settings.admin_login_max_attempts,
            window_seconds=settings.admin_login_window_seconds,
            lockout_seconds=settings.admin_login_lockout_seconds,
        )
        if failure_result.locked:
            message = _t(
                request,
                "login.error_too_many_attempts",
                seconds=failure_result.lock_seconds_remaining,
            )
            status_code = 429
        else:
            remaining_attempts = max(0, settings.admin_login_max_attempts - failure_result.attempts)
            message = _t(request, "login.error_invalid_password", remaining=remaining_attempts)
            status_code = 401
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/login.html",
            context={
                "next_path": next_path,
                "error": message,
                "hide_admin_chrome": True,
            },
            status_code=status_code,
        )

    clear_login_failures(request)
    token = build_admin_auth_token(
        password=settings.admin_password,
        secret_key=settings.jwt_secret_key,
    )
    response = RedirectResponse(url=next_path, status_code=303)
    response.set_cookie(
        key=settings.admin_auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.admin_cookie_secure,
        samesite="lax",
        max_age=settings.admin_auth_cookie_ttl_seconds,
        path="/",
    )
    return response


@router.post("/admin/logout")
def admin_logout(request: Request):
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(key=request.app.state.settings.admin_auth_cookie_name, path="/")
    return response


@router.get("/admin")
def admin_dashboard(
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.dashboard()
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={"view": view},
    )


@router.get("/admin/stations")
def admin_stations(
    request: Request,
):
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/stations/create")
def create_station(
    station_name: str = Form(...),
    station_id: str | None = Form(None),
    expected_judge_name: str | None = Form(None),
    credential: str | None = Form(None),
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    created = use_cases.views.create_station(
        station_name=station_name,
        station_id=station_id,
        expected_judge_name=expected_judge_name,
        credential=credential,
        actor=actor,
    )
    return RedirectResponse(
        url=f"/admin/stations/{created.station_id}?reveal=1",
        status_code=303,
    )


@router.get("/admin/stations/{station_id}")
def admin_station_detail(
    station_id: str,
    request: Request,
    reveal: bool = False,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/station_detail.html",
        context=_build_station_detail_context(
            request=request,
            use_cases=use_cases,
            station_id=station_id,
            reveal=reveal,
        ),
    )


@router.post("/admin/stations/{station_id}/rotate-credential")
def rotate_station_credential(
    station_id: str,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    use_cases.views.rotate_station_credential(station_id, actor=actor)
    return RedirectResponse(url=f"/admin/stations/{station_id}?reveal=1", status_code=303)


@router.post("/admin/stations/{station_id}/delete")
def delete_station(
    station_id: str,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    use_cases.views.delete_station(station_id, actor=actor)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/stations/{station_id}/sessions/{session_id}/kick")
async def kick_station_judge_session(
    station_id: str,
    session_id: str,
    reason: str = Form("operator_replaced"),
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    if use_cases.kick_judge_session is None:
        raise DomainError("Kick judge use case is not configured")

    await use_cases.kick_judge_session.execute(
        station_id=station_id,
        session_id=session_id,
        reason=reason,
        actor=actor,
    )
    return RedirectResponse(url=f"/admin/stations/{station_id}", status_code=303)


@router.get("/admin/stations/{station_id}/live-panel")
def station_live_panel(
    station_id: str,
    request: Request,
    auto_rotate: int = 0,
    reveal: int = 1,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    live = use_cases.views.station_live_snapshot(
        station_id=station_id,
        rotate_credential=bool(auto_rotate),
        actor="admin-live",
        reveal_credential=bool(reveal),
    )
    live_refresh_seconds = request.app.state.settings.admin_live_refresh_seconds
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/_station_live_panel.html",
        context={
            "live": live,
            "reveal": bool(reveal),
            "live_refresh_seconds": live_refresh_seconds,
            "station_qr_base64": _qr_base64(live.bootstrap_payload_json),
        },
    )


@router.get("/admin/stations/{station_id}/qr.png")
def station_qr_image(
    station_id: str,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    live = use_cases.views.station_live_snapshot(
        station_id=station_id,
        rotate_credential=False,
        actor="qr-export",
        reveal_credential=False,
    )
    image = qrcode.make(live.bootstrap_payload_json)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")


@router.get("/admin/stations/{station_id}/scoreboard")
def station_scoreboard(
    station_id: str,
    request: Request,
):
    return RedirectResponse(url=f"/scoreboard/{station_id}", status_code=303)


@router.get("/scoreboard/{station_id}")
def station_scoreboard_public(
    station_id: str,
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.station_scoreboard(station_id)
    refresh_seconds = max(1, request.app.state.settings.admin_live_refresh_seconds // 2)
    winner_overlay_seconds = max(1, request.app.state.settings.admin_live_winner_overlay_seconds)
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/station_scoreboard.html",
        context={
            "view": view,
            "active_match": use_cases.views.active_match(station_id),
            "refresh_seconds": refresh_seconds,
            "winner_overlay_seconds": winner_overlay_seconds,
            "live_min_width_px": max(1, int(request.app.state.settings.live_min_width_px)),
            "hide_admin_chrome": True,
            "body_class": "bg-slate-950 text-white overflow-hidden",
            "is_debug": False,
        },
    )


@router.get("/admin/stations/{station_id}/scoreboard/debug")
def station_scoreboard_debug(
    station_id: str,
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.station_scoreboard(station_id)
    refresh_seconds = max(1, request.app.state.settings.admin_live_refresh_seconds // 2)
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/station_scoreboard_debug.html",
        context={
            "view": view,
            "active_match": use_cases.views.active_match(station_id),
            "refresh_seconds": refresh_seconds,
            "hide_admin_chrome": True,
            "body_class": "text-slate-900",
            "is_debug": True,
        },
    )


@router.get("/admin/stations/{station_id}/active-match")
def station_active_match(
    station_id: str,
    reveal: int = 0,
):
    return RedirectResponse(
        url=f"/admin/stations/{station_id}?reveal={reveal}#active-match",
        status_code=303,
    )


@router.get("/admin/stations/{station_id}/active-match/panel")
def station_active_match_panel(
    station_id: str,
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/_active_match_panel.html",
        context=_build_active_match_context(
            request=request,
            use_cases=use_cases,
            station_id=station_id,
        ),
    )


@router.get("/admin/stations/{station_id}/match-admin")
def station_match_admin(
    station_id: str,
    reveal: int = 0,
):
    return RedirectResponse(
        url=f"/admin/stations/{station_id}?reveal={reveal}#start-match",
        status_code=303,
    )


@router.post("/admin/stations/{station_id}/matches/draw")
def draw_station_match_poomsaes(
    station_id: str,
    request: Request,
    competitor_left_name: str = Form("Red"),
    competitor_right_name: str = Form("Blue"),
    category_id: str = Form(""),
    selected_poomsaes: list[str] | None = Form(None),
    total_rounds: int = Form(2),
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    form_data = {
        "competitor_left_name": competitor_left_name,
        "competitor_right_name": competitor_right_name,
        "category_id": category_id,
        "selected_poomsaes": selected_poomsaes or [],
        "total_rounds": total_rounds,
    }

    try:
        draw_preview = use_cases.views.draw_station_match_poomsaes(
            station_id=station_id,
            category_id=category_id,
            selected_poomsaes=selected_poomsaes or [],
            total_rounds=total_rounds,
            actor=actor,
            competitor_left_name=competitor_left_name,
            competitor_right_name=competitor_right_name,
        )
    except DomainError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/station_detail.html",
            context=_build_station_detail_context(
                request=request,
                use_cases=use_cases,
                station_id=station_id,
                reveal=False,
                start_error=str(exc),
                draw_preview=None,
                form_data=form_data,
            ),
            status_code=422,
        )

    return _templates(request).TemplateResponse(
        request=request,
        name="admin/station_detail.html",
        context=_build_station_detail_context(
            request=request,
            use_cases=use_cases,
            station_id=station_id,
            reveal=False,
            start_error=None,
            draw_preview=draw_preview,
            form_data=form_data,
        ),
    )


@router.post("/admin/stations/{station_id}/matches/draw-preview")
def draw_station_match_poomsaes_preview(
    station_id: str,
    competitor_left_name: str = Form("Red"),
    competitor_right_name: str = Form("Blue"),
    category_id: str = Form(""),
    selected_poomsaes: list[str] | None = Form(None),
    total_rounds: int = Form(2),
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        draw_preview = use_cases.views.draw_station_match_poomsaes(
            station_id=station_id,
            category_id=category_id,
            selected_poomsaes=selected_poomsaes or [],
            total_rounds=total_rounds,
            actor=actor,
            competitor_left_name=competitor_left_name,
            competitor_right_name=competitor_right_name,
        )
    except DomainError as exc:
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc)},
        )

    return JSONResponse(
        content={
            "categoryId": draw_preview.category_id,
            "categoryLabel": draw_preview.category_label,
            "totalRounds": draw_preview.total_rounds,
            "drawnPoomsaes": draw_preview.drawn_poomsaes,
        }
    )


@router.post("/admin/stations/{station_id}/matches/save-competitors")
def save_station_match_competitors(
    station_id: str,
    request: Request,
    competitor_left_name: str = Form(...),
    competitor_right_name: str = Form(...),
    category_id: str = Form(""),
    selected_poomsaes: list[str] | None = Form(None),
    drawn_poomsaes: list[str] | None = Form(None),
    total_rounds: int = Form(2),
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        use_cases.views.save_station_match_competitors(
            station_id=station_id,
            competitor_left_name=competitor_left_name,
            competitor_right_name=competitor_right_name,
            actor=actor,
        )
    except DomainError as exc:
        form_data = {
            "competitor_left_name": competitor_left_name,
            "competitor_right_name": competitor_right_name,
            "category_id": category_id,
            "selected_poomsaes": selected_poomsaes or [],
            "drawn_poomsaes": drawn_poomsaes or [],
            "total_rounds": total_rounds,
        }
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/station_detail.html",
            context=_build_station_detail_context(
                request=request,
                use_cases=use_cases,
                station_id=station_id,
                reveal=False,
                start_error=str(exc),
                draw_preview=None,
                form_data=form_data,
            ),
            status_code=422,
        )

    return RedirectResponse(
        url=f"/admin/stations/{station_id}#start-match",
        status_code=303,
    )


@router.post("/admin/stations/{station_id}/matches/start")
def start_station_match(
    station_id: str,
    request: Request,
    competitor_left_name: str = Form(...),
    competitor_right_name: str = Form(...),
    category_id: str = Form(...),
    selected_poomsaes: list[str] | None = Form(None),
    drawn_poomsaes: list[str] | None = Form(None),
    total_rounds: int = Form(2),
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        use_cases.views.start_match(
            station_id=station_id,
            competitor_left_name=competitor_left_name,
            competitor_right_name=competitor_right_name,
            category_id=category_id,
            selected_poomsaes=selected_poomsaes or [],
            drawn_poomsaes=drawn_poomsaes or None,
            total_rounds=total_rounds,
            actor=actor,
        )
    except DomainError as exc:
        form_data = {
            "competitor_left_name": competitor_left_name,
            "competitor_right_name": competitor_right_name,
            "category_id": category_id,
            "selected_poomsaes": selected_poomsaes or [],
            "drawn_poomsaes": drawn_poomsaes or [],
            "total_rounds": total_rounds,
        }
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/station_detail.html",
            context=_build_station_detail_context(
                request=request,
                use_cases=use_cases,
                station_id=station_id,
                reveal=False,
                start_error=str(exc),
                draw_preview=None,
                form_data=form_data,
            ),
            status_code=422,
        )

    return RedirectResponse(
        url=f"/admin/stations/{station_id}#active-match",
        status_code=303,
    )


@router.post("/admin/stations/{station_id}/active-match/start-round")
def start_active_round(
    station_id: str,
    request: Request,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        use_cases.views.start_active_round(station_id=station_id, actor=actor)
    except DomainError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/station_detail.html",
            context=_build_station_detail_context(
                request=request,
                use_cases=use_cases,
                station_id=station_id,
                control_error=str(exc),
                reveal=False,
            ),
            status_code=422,
        )
    return RedirectResponse(url=f"/admin/stations/{station_id}#active-match", status_code=303)


@router.post("/admin/stations/{station_id}/active-match/stop-round")
def stop_active_round(
    station_id: str,
    request: Request,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        use_cases.views.stop_active_round(station_id=station_id, actor=actor)
    except DomainError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/station_detail.html",
            context=_build_station_detail_context(
                request=request,
                use_cases=use_cases,
                station_id=station_id,
                control_error=str(exc),
                reveal=False,
            ),
            status_code=422,
        )
    return RedirectResponse(url=f"/admin/stations/{station_id}#active-match", status_code=303)


@router.post("/admin/stations/{station_id}/active-match/pause-timer")
def pause_active_round_timer(
    station_id: str,
    request: Request,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        use_cases.views.pause_active_round_timer(station_id=station_id, actor=actor)
    except DomainError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/station_detail.html",
            context=_build_station_detail_context(
                request=request,
                use_cases=use_cases,
                station_id=station_id,
                control_error=str(exc),
                reveal=False,
            ),
            status_code=422,
        )
    return RedirectResponse(url=f"/admin/stations/{station_id}#active-match", status_code=303)


@router.post("/admin/stations/{station_id}/active-match/reset-round")
def reset_active_round(
    station_id: str,
    request: Request,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        use_cases.views.reset_active_round(station_id=station_id, actor=actor)
    except DomainError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/station_detail.html",
            context=_build_station_detail_context(
                request=request,
                use_cases=use_cases,
                station_id=station_id,
                control_error=str(exc),
                reveal=False,
            ),
            status_code=422,
        )
    return RedirectResponse(url=f"/admin/stations/{station_id}#active-match", status_code=303)


@router.post("/admin/stations/{station_id}/active-match/finalize")
def finalize_active_match(
    station_id: str,
    request: Request,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        use_cases.views.finalize_active_match(station_id=station_id, actor=actor)
    except DomainError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="admin/station_detail.html",
            context=_build_station_detail_context(
                request=request,
                use_cases=use_cases,
                station_id=station_id,
                control_error=str(exc),
                reveal=False,
            ),
            status_code=422,
        )
    return RedirectResponse(url=f"/admin/stations/{station_id}#active-match", status_code=303)


@router.get("/admin/stations/{station_id}/scoreboard/live")
def station_scoreboard_live_panel(
    station_id: str,
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.station_scoreboard(station_id)
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/_station_scoreboard_panel.html",
        context={
            "view": view,
            "active_match": use_cases.views.active_match(station_id),
            "is_debug": False,
        },
    )


@router.get("/scoreboard/{station_id}/live")
def station_scoreboard_public_live_panel(
    station_id: str,
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.station_scoreboard(station_id)
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/_station_scoreboard_panel.html",
        context={
            "view": view,
            "active_match": use_cases.views.active_match(station_id),
            "is_debug": False,
        },
    )


@router.get("/admin/stations/{station_id}/scoreboard/debug/live")
def station_scoreboard_debug_live_panel(
    station_id: str,
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.station_scoreboard(station_id)
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/_station_scoreboard_debug_panel.html",
        context={
            "view": view,
            "active_match": use_cases.views.active_match(station_id),
            "is_debug": True,
        },
    )


@router.get("/admin/matches/{match_id}")
def admin_match_detail(
    match_id: str,
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.match_detail(match_id)
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/match_detail.html",
        context={"view": view},
    )


@router.get("/admin/results")
def admin_results(
    request: Request,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.results()
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/results.html",
        context={"view": view},
    )


@router.get("/admin/history")
def admin_history(
    request: Request,
    notice: str | None = None,
    error: str | None = None,
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    view = use_cases.views.history()
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/history.html",
        context={"view": view, "notice": notice, "error": error},
    )


@router.post("/admin/history/{match_id}/delete")
def admin_history_delete_match(
    match_id: str,
    request: Request,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    try:
        use_cases.views.delete_history_match(match_id=match_id, actor=actor)
    except DomainError as exc:
        return RedirectResponse(url=f"/admin/history?error={quote_plus(str(exc))}", status_code=303)
    notice = quote_plus(_t(request, "history.notice_deleted_one"))
    return RedirectResponse(url=f"/admin/history?notice={notice}", status_code=303)


@router.post("/admin/history/delete-all")
def admin_history_delete_all(
    request: Request,
    actor: str = Form("local-admin"),
    use_cases: AdminUseCases = Depends(get_admin_use_cases),
):
    deleted, skipped_active = use_cases.views.delete_all_history_matches(actor=actor)
    notice = _t(
        request,
        "history.notice_deleted_all",
        deleted=deleted,
        skipped=skipped_active,
    )
    return RedirectResponse(url=f"/admin/history?notice={quote_plus(notice)}", status_code=303)
