def create_desktop_application():
    from .app import create_desktop_application as _create_desktop_application

    return _create_desktop_application()


def run_desktop_application():
    from .app import run_desktop_application as _run_desktop_application

    return _run_desktop_application()


__all__ = ["create_desktop_application", "run_desktop_application"]
