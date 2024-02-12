# pylint: disable=missing-docstring,attribute-defined-outside-init,broad-exception-caught
# pylint: disable=invalid-name
# Copyright 2018 Linus S
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
"""Calendar skill for OVOS"""
import datetime
import time

import arrow
import caldav
import ics
import vobject
import yaml
from ovos_bus_client.message import Message
from lingua_franca.format import nice_date, nice_time
from lingua_franca.parse import extract_datetime, normalize
from ovos_utils.time import now_local
from ovos_workshop.decorators import intent_handler
from ovos_workshop.filesystem import FileSystemAccess
from ovos_workshop.skills import OVOSSkill


class CalendarSkills(OVOSSkill):
    def update_credentials(self):
        self.server = False  # False for an ics file, true for a caldav server -regardless of where the creds are stored
        self.no_creds = False

        server_type = self.settings.get("server_type")
        if server_type == "server":  # On home
            self.server = True

            self.user = self.settings.get("username")
            self.server_address = self.settings.get("server_address")
            self.port = self.settings.get("port")
            self.password = self.settings.get("password")
            if self.user is None or self.user == "":
                # Using pw in config
                fs = FileSystemAccess(str(self.skill_id))
                if fs.exists("calendar_conf.yml"):
                    #  Use yml file for config
                    config = self.read_file("calendar_conf.yml")
                    config = yaml.safe_load(config)
                    self.user = config.get("username")
                    self.server_address = config.get("server_address")
                    self.port = config.get("port")
                    self.password = config.get("password")
                else:
                    self.no_creds = True
                if self.user is None or self.user == "":
                    self.no_creds = True
        elif server_type == "local":  # Use file
            pass

        if self.no_creds is True:
            # Not set up in file/home
            self.speak_dialog("setup")
            return False
        return True

    def initialize(self):
        self.update_credentials()

    @intent_handler('DayAppointment.intent')
    def handle_day_appoint(self, message: Message):
        # clean/get date in utter
        if self.update_credentials() is False:  # No credentials
            return
        utter = message.data["utterance"]
        when = extract_datetime(utter, datetime.datetime.now(), self.lang)[0]
        if when is None:
            when = extract_datetime("today", datetime.datetime.now(), self.lang)
        self.log.info(str(when))
        # get events
        events = self.get_events(when)
        nice_when = nice_date(when, now=now_local(), lang=self.lang)
        if events:
            # say first
            self.speak_dialog("day", data={"num_events": len(events), "event": events[0].get("event"),
                                           "when": nice_when,
                                           "time": nice_time(events[0].get("datetime"), use_ampm=True)})
            # Say follow up
            for x in range(1, len(events)):
                self.speak_dialog("day.followed", data={"event": events[x].get("event"),
                                                        "time": nice_time(events[x].get("datetime"), use_ampm=True)})
        elif events is None or events == []:
            self.speak_dialog("no.events", data={"when": nice_when})

    @intent_handler('NumAppointments.intent')
    def handle_num_appoint(self, message: Message):
        if self.update_credentials() is False:  # No credentials
            return
        # clean/get date in utter
        utter = message.data["utterance"]
        when = extract_datetime(utter, datetime.datetime.now(), self.lang)[0]
        if when is None:
            when = extract_datetime("today", datetime.datetime.now(), self.lang)
        self.log.info(str(when))
        # get events
        events = self.get_events(when)
        nice_when = nice_date(when, now=now_local(), lang=self.lang)
        if events:
            num_events = len(events)
            if num_events == 1:
                self.speak_dialog("num.event", data={"when": nice_when})
            else:
                self.speak_dialog("num.events", data={"num_events": num_events, "when": nice_when})
        elif events is None or events == []:
            self.speak_dialog("no.events", data={"when": nice_when})

    @intent_handler("AddAppointment.intent")
    def handle_add_appoint(self, message: Message):
        if self.update_credentials() is False:  # No credentials
            return

        event = message.data.get("event")
        while not event:
            # We need to get the event
            event = self.get_response("new.event.name")

        utterance = message.data['utterance']
        date, rest = extract_datetime(utterance, datetime.datetime.now(), self.lang)
        while rest == normalize(utterance):
            utterance = self.get_response("new.event.date")
            date, rest = extract_datetime(utterance, datetime.datetime.now(), self.lang)

        # Clean the date being in the event
        test_date, rest = extract_datetime(event, datetime.datetime.now(), self.lang)
        if test_date is not None:
            date_said = event.replace(rest, '')
            event = event.replace(date_said, '')

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
        if self.server is True:
            # start creating a vevent:
            cal = vobject.iCalendar()
            cal.add("vevent")
            # add name
            cal.vevent.add("summary").value = str(event)
            # add date
            cal.vevent.add('dtstart').value = date
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

        elif self.server is False:
            # Local
            # The calendar is on the device
            # Check if it needs to be made...
            fs = FileSystemAccess(str(self.skill_id))
            if fs.exists("calendar.ics"):
                # YAY! exists
                calendar = self.read_file("calendar.ics")
                c = ics.Calendar(calendar)
                e = ics.Event()
                # add event
                e.name = str(event)
                e.begin = str(arrow.get(date))
                c.events.add(e)
                self.write_file("calendar.ics", str(c))
                self.speak_dialog("new.event.summary", data={"event": str(event)})
            else:
                # create calendar
                c = ics.Calendar()
                e = ics.Event()
                # add event
                e.name = str(event)
                e.begin = str(arrow.get(date))
                c.events.add(e)
                self.write_file("calendar.ics", str(c))
                self.speak_dialog("new.event.summary", data={"event": str(event)})

    def get_events(self, date):
        """Get events on a date and return them as a list.
        date: Date object!
        Returns:
        list: {"datetime", "event"}
        """
        if self.server is False:
            events = []
            # The calendar is on the device
            # Check if it needs to be made...
            fs = FileSystemAccess(str(self.skill_id))
            if fs.exists("calendar.ics"):
                # YAY! exists
                calendar = self.read_file("calendar.ics")
                c = ics.Calendar(imports=calendar)
                for event in c.timeline.on(day=arrow.get(date)):
                    event_dict = {"datetime": event.begin.datetime, "event": event.name}
                    events.append(event_dict)
                return events
            else:
                return []

        elif self.server is True:
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
                            event_dict = {"datetime": cal.vevent.dtstart.value,
                                          "event": cal.vevent.summary.valueRepr()}
                            events.append(event_dict)
                return events

            except Exception as err:
                self.log.error("Error logging in: %s", err)
                self.speak_dialog("error.logging.in")
                return None

        else:
            raise ValueError("Wrong input")

    def check_for_time(self, dt):
        """Check for if there is a datetime object
        dt: datetime object
        Output:
        True if there is a time
        False for no time"""
        try:
            return not dt.time() == datetime.time(0)
        except Exception as err:
            self.log.error("Exception caught: %s", err)
            return False

    def read_file(self, filename):
        fs = FileSystemAccess(str(self.skill_id))
        data_file = fs.open(filename, "r")
        data = data_file.read()
        data_file.close()
        return data

    def write_file(self, filename, data):
        fs = FileSystemAccess(str(self.skill_id))
        data_file = fs.open(filename, "w")
        data_file.writelines(data)
        data_file.close()
        return True
