import datetime
import json
import logging
import os
import shutil
import time
from functools import partial

import pytest
from aiohttp import ClientError
from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.powercalc.helpers import get_library_json_path, get_library_path
from custom_components.powercalc.power_profile.error import LibraryLoadingError, ProfileDownloadError
from custom_components.powercalc.power_profile.loader.remote import ENDPOINT_DOWNLOAD, ENDPOINT_LIBRARY, RemoteLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType
from tests.common import get_test_profile_dir

pytestmark = pytest.mark.skip_remote_loader_mocking


@pytest.fixture
def mock_aioresponse() -> aioresponses:
    with aioresponses() as m:
        yield m


@pytest.fixture
def mock_library_json_response(mock_aioresponse: aioresponses) -> None:
    local_library_path = get_library_json_path()
    with open(local_library_path) as f:
        library_json = json.load(f)

    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=200,
        payload=library_json,
    )


@pytest.fixture
async def remote_loader(hass: HomeAssistant, mock_library_json_response: None) -> RemoteLoader:
    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    await loader.initialize()
    return loader


@pytest.fixture
async def mock_download_profile_endpoints(mock_aioresponse: aioresponses) -> list[dict]:
    remote_files = [
        {
            "path": "color_temp.csv.gz",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/color_temp.csv.gz",
        },
        {
            "path": "hs.csv.gz",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/hs.csv.gz",
        },
        {
            "path": "model.json",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/model.json",
        },
    ]

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/signify/LCA001",
        status=200,
        payload=remote_files,
        repeat=True,
    )

    for remote_file in remote_files:
        with open(get_test_profile_dir("signify-LCA001") + f"/{remote_file['path']}", "rb") as f:
            mock_aioresponse.get(
                remote_file["url"],
                status=200,
                body=f.read(),
                repeat=True,
            )
    return remote_files


async def test_download(mock_aioresponse: aioresponses, remote_loader: RemoteLoader, mock_download_profile_endpoints: list[dict]) -> None:
    """Mock the API response for the download of a profile."""
    remote_files = mock_download_profile_endpoints

    storage_dir = get_test_profile_dir("download")
    await remote_loader.download_profile("signify", "LCA001", storage_dir)

    for remote_file in remote_files:
        assert os.path.exists(os.path.join(storage_dir, remote_file["path"]))


async def test_download_with_parenthesis(remote_loader: RemoteLoader, mock_aioresponse: aioresponses) -> None:
    remote_files = [
        {
            "path": "model.json",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/google/Home Mini (HOA)/model.json",
        },
    ]

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/google/Home Mini (HOA)",
        status=200,
        payload=remote_files,
        repeat=True,
    )

    for remote_file in remote_files:
        with open(get_library_path("google/Home Mini (HOA)") + f"/{remote_file['path']}", "rb") as f:
            mock_aioresponse.get(
                remote_file["url"],
                status=200,
                body=f.read(),
                repeat=True,
            )

    storage_dir = get_test_profile_dir("download")
    await remote_loader.download_profile("google", "Home Mini (HOA)", storage_dir)

    for remote_file in remote_files:
        assert os.path.exists(os.path.join(storage_dir, remote_file["path"]))


async def test_get_manufacturer_listing(remote_loader: RemoteLoader) -> None:
    manufacturers = await remote_loader.get_manufacturer_listing(DeviceType.LIGHT)
    assert "signify" in manufacturers
    assert len(manufacturers) > 40


async def test_get_model_listing(remote_loader: RemoteLoader) -> None:
    models = await remote_loader.get_model_listing("signify", DeviceType.LIGHT)
    assert "LCT010" in models
    assert len(models) > 40


async def test_load_model_raises_library_exception_on_non_existing_model(remote_loader: RemoteLoader) -> None:
    with pytest.raises(LibraryLoadingError):
        await remote_loader.load_model("signify", "NON_EXISTING_MODEL")


async def test_download_profile_exception_unexpected_status_code(mock_aioresponse: aioresponses, remote_loader: RemoteLoader) -> None:
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/signify/LCA001",
        status=500,
        repeat=True,
    )

    with pytest.raises(ProfileDownloadError):
        await remote_loader.download_profile("signify", "LCA001", get_test_profile_dir("download"))


async def test_exception_is_raised_on_connection_error(mock_aioresponse: aioresponses, remote_loader: RemoteLoader) -> None:
    mock_aioresponse.get(f"{ENDPOINT_DOWNLOAD}/signify/LCA001", exception=ClientError("test"))

    with pytest.raises(ProfileDownloadError):
        await remote_loader.download_profile("signify", "LCA001", get_test_profile_dir("download"))


async def test_exception_is_raised_on_github_resource_unavailable(mock_aioresponse: aioresponses, remote_loader: RemoteLoader) -> None:
    manufacturer = "signify"
    model = "LCA001"
    storage_path = remote_loader.get_storage_path(manufacturer, model)
    clear_storage_dir(storage_path)

    remote_file = {
        "path": "color_temp.csv.gz",
        "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/color_temp.csv.gz",
    }

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}",
        status=200,
        payload=[remote_file],
        repeat=True,
    )

    mock_aioresponse.get(
        remote_file["url"],
        status=500,
        repeat=True,
    )

    remote_loader.retry_timeout = 0
    with pytest.raises(ProfileDownloadError):
        await remote_loader.load_model(manufacturer, model)


async def test_eventual_success_after_download_retry(mock_aioresponse: aioresponses, remote_loader: RemoteLoader) -> None:
    manufacturer = "signify"
    model = "LCA001"
    storage_path = remote_loader.get_storage_path(manufacturer, model)
    clear_storage_dir(storage_path)

    remote_file = {
        "path": "color_temp.csv.gz",
        "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/color_temp.csv.gz",
    }

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}",
        status=200,
        payload=[remote_file],
        repeat=True,
    )

    mock_aioresponse.get(remote_file["url"], status=500)
    mock_aioresponse.get(remote_file["url"], status=200)

    callback = partial(remote_loader.download_profile, manufacturer, model, storage_path)
    await remote_loader.download_with_retry(callback)

    assert os.path.exists(storage_path)


@pytest.mark.parametrize(
    "remote_modification_time_delta,exists_locally,expected_download",
    [
        (-5000, False, True),
        (+400, True, True),
        (-4000, True, False),
    ],
)
async def test_profile_redownloaded_when_newer_version_available(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
    mock_download_profile_endpoints: None,
    remote_modification_time_delta: int,
    exists_locally: bool,
    expected_download: bool,
) -> None:
    def _count_download_requests() -> int:
        for req, calls in mock_aioresponse.requests.items():
            if str(req[1]).startswith(ENDPOINT_DOWNLOAD):
                return len(calls)
        return 0

    def _mock_library_json(profile_updated_at: str) -> None:
        mock_aioresponse.get(
            ENDPOINT_LIBRARY,
            status=200,
            payload={
                "manufacturers": [
                    {
                        "name": "signify",
                        "models": [
                            {
                                "id": "LCA001",
                                "device_type": "light",
                                "updated_at": profile_updated_at,
                            },
                        ],
                    },
                ],
            },
            repeat=True,
        )

    remote_date = datetime.datetime.fromtimestamp(time.time() + remote_modification_time_delta).isoformat()
    _mock_library_json(remote_date)

    loader = RemoteLoader(hass)
    await loader.initialize()

    # Clean local directory first so we have consistent test results
    # When scenario exists_locally=True, we download the profile first, to fake the local existence
    local_storage_path = loader.get_storage_path("signify", "LCA001")
    clear_storage_dir(local_storage_path)

    if exists_locally:
        await loader.set_last_update_time(time.time())
        await loader.download_profile("signify", "LCA001", local_storage_path)

    await loader.load_model("signify", "LCA001")

    expected_call_count = 1 if expected_download else 0
    if exists_locally:
        expected_call_count += 1
    assert _count_download_requests() == expected_call_count


async def test_fallback_to_local_library(hass: HomeAssistant, mock_aioresponse: aioresponses, caplog: pytest.LogCaptureFixture) -> None:
    """
    Test that the local library is used when the remote library is not available.
    When unavailable, it should retry 3 times before falling back to the local library.
    """

    shutil.copy(get_library_json_path(), hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json"))

    caplog.set_level(logging.WARNING)
    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=404,
        repeat=True,
    )

    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    await loader.initialize()

    assert "signify" in loader.manufacturer_models
    assert len(caplog.records) == 2


async def test_fallback_to_local_library_on_client_connection_error(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Test that the local library is used when api.powercalc.nl is not available.
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2277
    """
    shutil.copy(get_library_json_path(), hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json"))

    caplog.set_level(logging.WARNING)
    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=200,
        repeat=True,
        exception=ClientError("test"),
    )

    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    await loader.initialize()

    assert "signify" in loader.manufacturer_models
    assert len(caplog.records) == 2


async def test_fallback_to_local_library_fails(hass: HomeAssistant, mock_aioresponse: aioresponses, caplog: pytest.LogCaptureFixture) -> None:
    """
    After 3 retries, and the library.json is never downloaded before to .storage dir, it should raise a ProfileDownloadError.
    """

    os.remove(hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json"))

    caplog.set_level(logging.WARNING)
    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=404,
        repeat=True,
    )

    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    with pytest.raises(ProfileDownloadError):
        await loader.initialize()


async def test_fallback_to_local_profile(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
    mock_library_json_response: None,
    remote_loader: RemoteLoader,
) -> None:
    manufacturer = "signify"
    model = "LCA001"
    local_storage_path = remote_loader.get_storage_path(manufacturer, model)
    clear_storage_dir(local_storage_path)
    shutil.copytree(get_library_path(f"{manufacturer}/{model}"), local_storage_path)

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}",
        status=500,
        repeat=True,
    )

    await remote_loader.load_model(manufacturer, model, force_update=True)


async def test_profile_redownloaded_when_model_json_missing(
    hass: HomeAssistant,
    remote_loader: RemoteLoader,
    mock_download_profile_endpoints: list[dict],
) -> None:
    """Test profile is redownloaded when model.json is missing."""
    local_storage_path = remote_loader.get_storage_path("signify", "LCA001")
    shutil.rmtree(local_storage_path, ignore_errors=True)
    os.makedirs(local_storage_path)

    (__, storage_path) = await remote_loader.load_model("signify", "LCA001")
    assert storage_path == local_storage_path


async def test_profile_redownloaded_when_model_json_corrupt(
    hass: HomeAssistant,
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Corrupt the model.json file and check if it is redownloaded."""
    local_storage_path = remote_loader.get_storage_path("apple", "HomePod Mini")
    shutil.rmtree(local_storage_path, ignore_errors=True)
    os.makedirs(local_storage_path)

    remote_files = [
        {
            "path": "model.json",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/apple/HomePod Mini/model.json",
        },
    ]

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/apple/HomePod Mini",
        status=200,
        payload=remote_files,
        repeat=True,
    )

    mock_aioresponse.get(
        remote_files[0]["url"],
        status=200,
        body="invalid json",
    )
    with open(get_library_path("apple/HomePod Mini/model.json"), "rb") as f:
        mock_aioresponse.get(
            remote_files[0]["url"],
            status=200,
            body=f.read(),
        )

    await remote_loader.load_model("apple", "HomePod Mini")

    assert "model.json file is not valid JSON" in caplog.text
    assert "Retrying to load model.json file" in caplog.text


async def test_profile_redownloaded_when_model_json_corrupt_retry_limit(
    hass: HomeAssistant,
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    When model.json is corrupt, retry 3 times before giving up.
    After 3 times it should raise a LibraryLoadingError.
    """
    local_storage_path = remote_loader.get_storage_path("apple", "HomePod Mini")
    shutil.rmtree(local_storage_path, ignore_errors=True)
    os.makedirs(local_storage_path)

    remote_files = [
        {
            "path": "model.json",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/apple/HomePod Mini/model.json",
        },
    ]

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/apple/HomePod Mini",
        status=200,
        payload=remote_files,
        repeat=True,
    )

    mock_aioresponse.get(
        remote_files[0]["url"],
        status=200,
        body="invalid json",
        repeat=True,
    )

    with pytest.raises(LibraryLoadingError):
        await remote_loader.load_model("apple", "HomePod Mini")


async def test_find_model(remote_loader: RemoteLoader) -> None:
    model = await remote_loader.find_model("apple", {"HomePod (gen 2)"})
    assert model == "MQJ83"


async def test_find_model_returns_none(remote_loader: RemoteLoader) -> None:
    model = await remote_loader.find_model("apple", {"Non existing model"})
    assert model is None


def clear_storage_dir(storage_path: str) -> None:
    if not os.path.exists(storage_path):
        return
    shutil.rmtree(storage_path, ignore_errors=True)
