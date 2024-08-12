==============================
Virtual power sensor (library)
==============================

Powercalc has a huge library of power profiles which can be directly used without the need of extensive configuration.
For all supported devices please see the `supported models`_ listing.

Most of the time Powercalc will find compatible devices in your system and provide you with a discovery flow which you only need to accept.

When your device is not found or you want to reuse or force a certain profile for another device you can select the profile manually.

Follow the instruction below depending on your preferred configuration method GUI or YAML.

GUI
---

Just click the button to directly add a powercalc sensor:

.. image:: https://my.home-assistant.io/badges/config_flow_start.svg
   :target: https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc

Select :guilabel:`Virtual power (library)` and follow the instructions.

YAML
----

Just specify the correct manufacturer and model.

.. code-block:: yaml

    powercalc:
      sensors:
        - entity_id: light.my_light
          manufacturer: signify
          model: LCT010

Sub profiles
------------

Some power profiles provide multiple sub profiles.

Examples of that are:

- Led strips of multiple lengths
- Lights with a night vision / infrared mode
- Lights which have a separate up and down light
- Camera's with a night vision

Most power profiles can automatically switch to the correct sub profile depending on some entity and/or attribute state, but for some of them Powercalc can not known and you must select on manually.
This applies for example to extensible led strips of different lengths.

In the GUI flow this will be asked in the wizard as shown in screenshot below.

.. image:: /img/sub_profile.png

In YAML you'll need to append the sub profile to the model, separated by a slash:
For example to select sub profile `length_9` of LIFX Z model.

.. code-block:: yaml

    powercalc:
      sensors:
        - entity_id: light.my_light
          manufacturer: lifx
          model: LIFX Z/length_9

Powercalc also provides a service which you can call to switch to another sub profile while HA is running.
The service is called ``powercalc.switch_sub_profile``.
You can call this service from the GUI (:guilabel:`Developer tools` -> :guilabel:`Services`) or from automations.

.. code-block:: yaml

    service: powercalc.switch_sub_profile
    data:
      profile: length_5
    target:
      entity_id: sensor.my_light_power
