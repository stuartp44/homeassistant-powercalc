from homeassistant import data_entry_flow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc import SensorType
from custom_components.powercalc.config_flow import Steps
from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_GROUP,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_ON_TIME,
    CONF_SENSOR_TYPE,
    CONF_UPDATE_FREQUENCY,
    CONF_UTILITY_METER_TARIFFS,
    CONF_VALUE,
)
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    create_mock_entry,
    initialize_options_flow,
    select_menu_item,
)


async def test_daily_energy_mandatory_fields_not_supplied(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Steps.DAILY_ENERGY)

    user_input = {CONF_NAME: "My daily energy sensor"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"] == {"base": "daily_energy_mandatory"}


async def test_create_daily_energy_entry(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Steps.DAILY_ENERGY)

    user_input = {
        CONF_NAME: "My daily energy sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_VALUE: 0.5,
        CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
        CONF_CREATE_UTILITY_METERS: False,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
        CONF_NAME: "My daily energy sensor",
        CONF_DAILY_FIXED_ENERGY: {
            CONF_UPDATE_FREQUENCY: 1800,
            CONF_VALUE: 0.5,
            CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
        },
        CONF_CREATE_UTILITY_METERS: False,
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_daily_energy_sensor_energy")


async def test_daily_energy_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "My daily energy sensor",
            CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
            CONF_DAILY_FIXED_ENERGY: {CONF_VALUE: 50},
        },
    )

    result = await initialize_options_flow(hass, entry, Steps.DAILY_ENERGY)

    user_input = {CONF_VALUE: 75, CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DAILY_FIXED_ENERGY][CONF_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT
    assert entry.data[CONF_DAILY_FIXED_ENERGY][CONF_VALUE] == 75


async def test_on_time_option(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Steps.DAILY_ENERGY)

    user_input = {
        CONF_NAME: "My daily energy sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_VALUE: 10,
        CONF_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
        CONF_ON_TIME: {
            "hours": 10,
            "minutes": 20,
            "seconds": 30,
        },
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DAILY_FIXED_ENERGY][CONF_ON_TIME] == {
        "hours": 10,
        "minutes": 20,
        "seconds": 30,
    }


async def test_utility_meter_options(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Steps.DAILY_ENERGY)

    user_input = {
        CONF_NAME: "My daily energy sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_VALUE: 10,
        CONF_CREATE_UTILITY_METERS: True,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_UTILITY_METER_TARIFFS: ["peak", "offpeak"],
        },
    )

    config_entry: ConfigEntry = result["result"]

    result = await initialize_options_flow(hass, config_entry, Steps.UTILITY_METER_OPTIONS)

    user_input = {CONF_UTILITY_METER_TARIFFS: ["peak"]}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert config_entry.data[CONF_UTILITY_METER_TARIFFS] == ["peak"]


async def test_add_to_group(hass: HomeAssistant) -> None:
    group_entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "My group",
            CONF_SENSOR_TYPE: SensorType.GROUP,
        },
    )

    result = await select_menu_item(hass, Steps.DAILY_ENERGY)

    user_input = {
        CONF_NAME: "My daily energy sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_VALUE: 10,
        CONF_GROUP: group_entry.entry_id,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_GROUP] == group_entry.entry_id
    config_entry: ConfigEntry = result["result"]

    group_entry = hass.config_entries.async_get_entry(group_entry.entry_id)
    assert config_entry.entry_id in group_entry.data[CONF_GROUP_MEMBER_SENSORS]


async def test_can_set_basic_options(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
            CONF_NAME: "Test",
            CONF_CREATE_UTILITY_METERS: False,
            CONF_DAILY_FIXED_ENERGY: {CONF_VALUE: 50},
        },
    )

    result = await initialize_options_flow(hass, entry, Steps.BASIC_OPTIONS)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_CREATE_UTILITY_METERS: True},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_CREATE_UTILITY_METERS]
