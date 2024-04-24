"""Base class for calendar skills. Keeps properties tidy."""

import os

from ovos_config.locations import get_xdg_data_save_path
from ovos_workshop.skills import OVOSSkill

class BaseCalendarSkill(OVOSSkill):
    """Base class for calendar skills. Keeps properties tidy."""
    @property
    def server_type(self) -> str:
        """Get the server type for the calendar, either local or server. Invalid entries default to local."""
        return self.settings.get("server_type", "local")

    @property
    def user(self) -> str:
        """Get the username for the calendar, if remote."""
        return self.settings.get("username", "")

    @property
    def server_address(self) -> str:
        """Get the server address for the calendar, if remote."""
        self.settings.get("server_address", "")

    @property
    def port(self) -> str:
        """Get the port for the calendar, if remote."""
        return self.settings.get("port", "")

    @property
    def password(self) -> str:
        """Get the password for the calendar, if remote. Not stored securely."""
        return self.settings.get("password", "")

    @user.setter
    def user(self, value):
        self.settings["username"] = value

    @server_address.setter
    def server_address(self, value):
        self.settings["server_address"] = value

    @port.setter
    def port(self, value):
        self.settings["port"] = value

    @password.setter
    def password(self, value):
        self.settings["password"] = value

    @property
    def local_ics_location(self):
        """Get the location of the local ics file
        Default for Neon is ~/.local/share/neon/filesystem/calendar-skill.mikejgray/calendar.ics
        Default for OVOS is ~/.local/share/mycroft/filesystem/calendar-skill.mikejgray/calendar.ics
        """
        location = self.settings.get("local_ics_location", f'{get_xdg_data_save_path()}/filesystem/skills/{self.skill_id}')
        if not location.endswith(".ics"):
            location = os.path.join(location, "calendar.ics")
        if os.path.exists(location):
            # Check our permissions to see if we can write to it
            if not os.access(location, os.W_OK):
                self.log.warning(
                    "Local calendar file %s is not writeable. Read functions still work. Please check permissions and try again.",
                    location,
                )
        return location
