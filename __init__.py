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
#
from mycroft import MycroftSkill, intent_file_handler
from mycroft.util.parse import extract_datetime, normalize
from mycroft.filesystem import FileSystemAccess
from datetime import datetime, date, time
import caldav
import vobject
import ics
import arrow
from caldav.elements import dav, cdav


class Calendar(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
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
                account_config = self.config_core.get("calendar", {})
                self.user = account_config.get("username")
                self.password = account_config.get("password")
                self.server_address = account_config.get("server_address")
                self.port = account_config.get("port")
                if self.user is None or self.user == "":
                    self.no_creds = True
        elif server_type == "local":  # Use file
            pass

    def initalize(self):
        """Set up credentials"""

        if self.no_creds is True:
            # Not set up in file/home
            self.speak_dialog("setup")
            return

    @intent_file_handler('DayAppointment.intent')
    def handle_day_appoint(self, message):
        # clean/get date in utter
        utter = message.data["utterance"]
        date = extract_datetime(utter)[0].date()
        if date is None:
            date = extract_datetime("today").date()
        # get events
        events = self.get_events(date)
        if events:
            # say first
            self.speak_dialog("day", data={"num_events": len(events), "event": events[0].get("event")})
            # Say follow up
            for x in range(1, len(events)):
                self.speak_dialog("day.followed", data={"event": events[x].get("event")})
        elif events is None or events == []:
            self.speak_dialog("no.events")

    @intent_file_handler("AddAppointment.intent")
    def handle_add_appoint(self, message):
        event = message.data.get("event")
        while not event:
            # We need to get the event
            event = self.get_response("new.event.name")

        utterance = message.data['utterance']
        date, rest = extract_datetime(utterance, datetime.now(), self.lang)
        while rest == normalize(utterance):
            utterance = self.get_response("new.event.date")
            date, rest = extract_datetime(utterance)

        self.log.info(" Calendar skill new event: date: " + str(date) + " event: " + event)
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
            url = "http://{}:{}@{}:{}/".format(self.user, self.password, self.server_address, self.port)
            try:
                client = caldav.DAVClient(url)
                principal = client.principal()

                # Select calendar
                events = []
                for calendar in principal.calendars():
                    calendar.add_event(str(cal.serialize()))
                self.speak_dialog("new.event.summary", data={"event": str(event)})
            except:
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
            url = "http://{}:{}@{}:{}/".format(self.user, self.password, self.server_address, self.port)

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
                            event_dict = {"date": cal.vevent.dtstart.value.date(),
                                          "time": cal.vevent.dtstart.value.time(),
                                          "event": cal.vevent.summary.valueRepr()}
                            events.append(event_dict)
                return events

            except:
                self.speak_dialog("error.logging.in")
                return None

        else:
            raise("Wrong input")

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


def create_skill():
    return Calendar()
