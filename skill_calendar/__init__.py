# pylint: disable=missing-docstring,attribute-defined-outside-init,broad-exception-caught
# pylint: disable=invalid-name,bare-except
# Copyright 2018 Linus S
# Copyright 2024 Michael Gray
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Calendar skill for OVOS/Neon."""

import datetime
import os
import time
from typing import Optional

import arrow
import caldav
import ics
import vobject
import yaml
from lingua_franca.format import nice_date, nice_time
from lingua_franca.internal import load_language
from lingua_franca.parse import extract_datetime, normalize
from ovos_bus_client.message import Message
from ovos_utils.messagebus import FakeBus
from ovos_utils.time import now_local
from ovos_workshop.decorators import intent_handler

from skill_calendar.baseclass import BaseCalendarSkill


class CalendarSkill(BaseCalendarSkill):
    def initialize(self):
        load_language(self.lang)
        self.update_credentials()

    def update_credentials(self):
        self.server = False  # False for an ics file, true for a caldav server
        self.no_creds = False
        self.server = False
        if self.server_type == "server":
            self.log.error("Server type is server, but not yet implemented!")
        # if self.server_type == "local":  # Use file
        self.log.debug(
            "Using local calendar, searching for file and creating if it doesn't exist"
        )
        self._find_local_calendar()
        return True

    @intent_handler("DayAppointment.intent")
    def handle_day_appoint(self, message: Message):
        """Clean/get date in utterance"""
        # if self.update_credentials() is False:  # No credentials
        #     return
        spoken_when = message.data.get("when", "today")
        when = self._retrieve_datetime(spoken_when)
        # get events
        events = self.get_events(when)
        nice_when = nice_date(when, now=now_local(), lang=self.lang)
        if events:
            # say first
            self.speak_dialog(
                "day",
                data={
                    "num_events": len(events),
                    "event": events[0].get("event"),
                    "when": nice_when,
                    "time": nice_time(events[0].get("datetime"), use_ampm=True),
                },
            )
            # Say follow up
            for evt in range(1, len(events)):
                self.speak_dialog(
                    "day.followed",
                    data={
                        "event": events[evt].get("event"),
                        "time": nice_time(
                            events[evt].get("datetime"),
                            use_ampm=self.config_core["time_format"] == "half",
                        ),
                    },
                )
        else:
            self.speak_dialog("no.events", data={"when": nice_when})

    @intent_handler("NumAppointments.intent")
    def handle_num_appoint(self, message: Message):
        if self.update_credentials() is False:  # No credentials
            return
        # clean/get date in utter
        spoken_when = message.data.get("when", "today")
        when = self._retrieve_datetime(spoken_when)
        self.log.debug(str(when))
        # get events
        events = self.get_events(when)
        nice_when = nice_date(when, now=now_local(), lang=self.lang)
        if events:
            num_events = len(events)
            if num_events == 1:
                self.speak_dialog("num.event", data={"when": nice_when})
            else:
                self.speak_dialog(
                    "num.events", data={"num_events": num_events, "when": nice_when}
                )
        elif events is None or events == []:
            self.speak_dialog("no.events", data={"when": nice_when})

    @intent_handler("NextAppointment.intent")
    def handle_next_appoint(self, message: Message):
        events = self._next_x_events(100)
        if not events:
            self.speak_dialog("no.events.found", data={})
            return
        next_timed_event = self._find_next_timed_event(events)
        next_all_day_event = self._find_next_all_day_event(events)
        if next_timed_event:
            self.speak_dialog(
                "next.event",
                data={
                    "event": next_timed_event.name,
                    "when": nice_time(next_timed_event.begin),
                },
            )
            return
        if not next_timed_event and next_all_day_event:
            self.speak_dialog(
                "next.all.day.event", data={"event": next_all_day_event.name}
            )
            return

    @intent_handler("AddAppointment.intent")
    def handle_add_appoint(self, message: Message):
        event = self._get_event_at_all_costs(message)
        date = self._extract_event_datetime(message)
        # Clean the date being in the event
        event = self._clean_event_dates(event)

        # Check that there is a time - ask for one if there isn't
        if not self.check_for_time(date):
            this_time = None
            # No time- ask
            while self.check_for_time(this_time) is False:
                this_time = self.get_response("new.event.time", data={"event": event})
                this_time, _ = extract_datetime(this_time)

            # user said date: add to date object
            date = datetime.datetime.combine(date.date(), time.time())
        self.log.info("Calendar skill new event: date: %s event: %s", str(date), event)
        # ADD EVENT
        if self.server is False:
            self._add_event_to_calendar(event, date)
            self.speak_dialog("new.event.summary", data={"event": str(event)})
        if self.server is True:
            self.log.warning("Server not yet implemented, sorry!")

    def _add_event_to_calendar(self, event, date):
        e = ics.Event()
        # add event
        e.name = str(event)
        e.begin = str(arrow.get(date))
        self.log.debug("Adding event: %s", e.serialize())
        self.calendar.events.add(e)

    def _clean_event_dates(self, event):
        test_date = extract_datetime(event, datetime.datetime.now(), self.lang)
        if test_date is not None:
            date_said = event.replace(rest, "")
            event = event.replace(date_said, "")
        return event

    def _extract_event_datetime(self, message):
        utterance = message.data.get("utterance")
        date, rest = extract_datetime(utterance, datetime.datetime.now(), self.lang)
        while rest == normalize(utterance):
            utterance = self.get_response("new.event.date")
            date, rest = extract_datetime(utterance, datetime.datetime.now(), self.lang)
        return date

    def _get_event_at_all_costs(self, message):
        event = message.data.get("event")
        while not event:
            # We need to get the event
            event = self.get_response("new.event.name")
        return event
        # return self.add_caldav_event(event, date)

    def add_caldav_event(self, event, date):
        # start creating a vevent:
        cal = vobject.iCalendar()
        cal.add("vevent")
        # add name
        cal.vevent.add("summary").value = str(event)
        # add date
        cal.vevent.add("dtstart").value = date
        # add it to the calendar
        url = f"http://{self.user}:{self.password}@{self.server_address}:{self.port}/"
        try:
            client = caldav.DAVClient(url)
            principal = client.principal()

            # Select calendar
            for calendar in principal.calendars():
                calendar.add_event(str(cal.serialize()))
            self.speak_dialog("new.event.summary", data={"event": str(event)})
        except Exception as err:
            self.log.error(err)
            self.speak_dialog("error.logging.in")
            return None

    def get_events(self, date: Optional[datetime.datetime]):
        """Get events on a date and return them as a list.
        date: Date object!
        Returns:
        list: {"datetime", "event"}
        """
        if not date:
            date = datetime.datetime.now()
        if self.server is True:
            return self._get_remote_events(date)
        return self._get_local_events(date)

    def check_for_time(self, dt):
        """Check for if there is a datetime object
        dt: datetime object
        Output:
        True if there is a time
        False for no time"""
        try:
            return not dt.time() == datetime.time(0)
        except Exception:
            self.log.exception(
                "Exception caught while checking for a time in a datetime object"
            )
            return False

    def _read_file(self, filepath):
        with open(filepath, "r", encoding="utf-8") as data_file:
            data = data_file.read()
        return data

    def _write_file(self, filepath, data):
        try:
            with open(filepath, "w", encoding="utf-8") as data_file:
                data_file.writelines(data)
            return True
        except:
            self.log.exception("Error writing to file %s", filepath)
            return False

    def _retrieve_datetime(self, spoken_when):
        when = extract_datetime(spoken_when)
        if isinstance(when, list) and len(when):
            when = when[0]
        else:
            when = datetime.datetime.now()
        return when

    def _extract_datetime(self, utter: str) -> datetime.datetime:
        when = extract_datetime(utter, datetime.datetime.now(), self.lang)
        if when is None:
            self.log.info(
                "No datetime found in utterance %s, defaulting to today", utter
            )
            when = extract_datetime("today", datetime.datetime.now(), self.lang)
        if isinstance(when, list):
            when = when[0]
        self.log.debug("Extracted datetime from utterance %s: %s", utter, str(when))
        return when

    def _create_local_calendar(self) -> bool:
        try:
            c = ics.Calendar()
            self._write_file(self.local_ics_location, str(c))
            self.calendar: ics.Calendar = c
            return True
        except Exception:
            self.log.exception(
                "Error creating local calendar %s", self.local_ics_location
            )
            return False

    def _find_local_calendar(self) -> bool:
        if os.path.exists(self.local_ics_location):
            self.log.info("Local calendar exists at %s", self.local_ics_location)
            calendar = self._read_file(self.local_ics_location)
            self.calendar = ics.Calendar(imports=calendar)
            return True
        else:
            self.log.info(
                "Local calendar does not exist at %s, creating one",
                self.local_ics_location,
            )
            successfully_created_calendar = self._create_local_calendar()
            if successfully_created_calendar:
                return True
            return False

    def _get_local_events(self, date):
        """If the calendar is on the device"""
        events = []
        for event in self.calendar.timeline.on(day=arrow.get(date)):
            event_dict = {"datetime": event.begin.datetime, "event": event.name}
            events.append(event_dict)
        return events or []

    def _get_remote_events(self, date):  # TODO: Refactor all this remote stuff
        url = f"http://{self.user}:{self.password}@{self.server_address}:{self.port}/"

        try:
            client = caldav.DAVClient(url)
            principal = client.principal()

            # Select calendar
            events = []
            for calendar in principal.calendars():
                for event in calendar.events():
                    event_text = event.data
                    cal = vobject.readOne(event_text)
                    event_date = cal.vevent.dtstart.value.date()
                    # If in date, append.
                    if event_date == date:
                        event_dict = {
                            "datetime": cal.vevent.dtstart.value,
                            "event": cal.vevent.summary.valueRepr(),
                        }
                        events.append(event_dict)
            return events

        except Exception as err:
            self.log.error("Error logging in: %s", err)
            self.speak_dialog("error.logging.in")
            return None

    def _set_server_config_from_yaml(self):
        config = self._read_file("calendar_conf.yml")
        config = yaml.safe_load(config)
        self.user = config.get("username", self.user)
        self.server_address = config.get("server_address", self.server_address)
        self.port = config.get("port", self.port)
        self.password = config.get("password", self.password)

    def _find_next_timed_event(self, events: list[ics.Event]) -> Optional[ics.Event]:
        timed_event = [x for x in events if not x.all_day]
        return timed_event[0] if len(timed_event) else None

    def _find_next_all_day_event(self, events: list[ics.Event]) -> Optional[ics.Event]:
        timed_event = [x for x in events if x.all_day]
        return timed_event[0] if len(timed_event) else None

    def _next_x_events(self, num_events: int) -> list[ics.Event]:
        return list(
            self.calendar.timeline.start_after(arrow.get(datetime.datetime.now()))
        )[:num_events]


if __name__ == "__main__":
    x = CalendarSkill(
        bus=FakeBus(),
        skill_id="skill-calendar.mikejgray",
        settings={
            "local_ics_location": "/Users/Mike/.config/mycroft/skills/skill-calendar.mikejgray/calendar.ics"
        },
    )
    # x._get_local_events(datetime.datetime.now())
    # x._get_local_events(extract_datetime("what is on my calendar tomorrow?"))
    # x.handle_next_appoint(None)
    x.handle_add_appoint(
        Message(
            "blah.blah",
            {"event": "test event", "utterance": "schedule test event tomorrow at 3pm"},
        )
    )
