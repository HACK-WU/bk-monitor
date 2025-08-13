from drf_resource.utils.local import local


def get_request(peaceful=False):
    if hasattr(local, "current_request"):
        return local.current_request
    elif peaceful:
        return None

    raise Exception("get_request: current thread hasn't request.")
