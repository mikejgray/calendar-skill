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
import ics
import arrow
import vobject
from caldav.elements import dav, cdav

#For creating calendars
new_vcal = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{summary}
END:VEVENT
END:VCALENDAR
"""

#For already created calendars
new_vcal = """
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{summary}
END:VEVENT
"""

class Calendar(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

    @intent_file_handler('DayAppointment.intent')
    def handle_day_appoint(self, message):
        #clean/get date in utter
        utter = message.data["utterance"]
        date = extract_datetime(utter)[0].date()
        if date == None:
            date = extract_datetime("today").date()
        #get events
        events = self.get_events(date)
        if events:
            #say first
            self.speak_dialog("day", data={"num_events":len(events), "event":events[0].get("event")})
            #Say follow up
            for x in range(1, len(events)):
                self.speak_dialog("day.followed", data={"event": events[x].get("event")})
        elif events == None or events == []:
            self.speak_dialog("no.events")
        elif events == "Handled":
            pass

    @intent_file_handler("AddAppointment.intent")
    def handle_add_appoint(self, message):
        event = message.data.get("event")
        while not  event:
            #We need to get the event
            event = self.get_response("new.event.name")
        utter = message.data["utterance"]
        date, rest = extract_datetime(utter)
        while rest == normalize(utter):
            #We need to get the date
            resp = self.get_response("new.event.date")
            date, rest = extract_datetime(utter)
        self.log.critical("date: "+ str(date)+ " event: "+event)
        #ADD EVENT
        server_type = self.check_server()
        if server_type == "Handled":
            return
        elif server_type == True:
            #Home
            pass
        elif server_type == None:
            #Password local
            pass
        elif server_type == False:
            #Local
            #The calendar is on the device
            #Check if it needs to be made...
            fs = FileSystemAccess(str(self.skill_id))
            if fs.exists("calendar.ics"):
                #YAY! exists
                calendar = self.read_file("calendar.ics")
                c = ics.Calendar(calendar)
                e = ics.Event()
                #add event
                e.name = str(event)
                e.begin = str(arrow.get(date))
                c.events.append(e)
                self.write_file("calendar.ics", c)
                self.speak_dialog("new.event.summary")
            else:
                #create calendar
                pass

    def check_server(self):
        """Check if we are using file/server or direct user to setup

        True for server
        None for server -> password on device
        False for local"""
        server_type = self.settings.get("server_type")
        if server_type == "local":
            return False
        if server_type == "server":
            user = self.settings.get("username")
            if user == None or user == "":
                account_config = self.config_core.get("calendar", {})
                user_local = account_config.get("username")
                if user_local == "" or user_local == None:
                    self.sepak_dialog("setup")
                    return "Handled"
                else:
                    return None
            else:
                return True

    def get_events(self, date):
        """Get events on a date and return them as a list.
        date: Date object!
        Returns:
        list: {"datetime", "event"}
        """
        server_type = self.check_server()
        if server_type == "Handled":
            #Do nothing
            return "Handled"
        elif server_type == False:
            events = []
            #The calendar is on the device
            #Check if it needs to be made...
            fs = FileSystemAccess(str(self.skill_id))
            if fs.exists("calendar.ics"):
                #YAY! exists
                calendar = self.read_file("calendar.ics")
                c = ics.Calendar(calendar)
                for event in c.events:
                    event_date = event.begin.datetime
                    if event_date.date() == date:
                        event_dict = {"datetime": event.begin.datetime, "event": event.name}
                        events.append(event_dict)
                return events
            else:
                return []

        elif server_type == True:
            #Get server and password info from home
            server_address = self.settings.get("server_address")
            port = self.settings.get("port")
            username = self.settings.get("username")
            password = self.settings.get("password")

            url = "http://{}:{}@{}:{}/".format(username, password, server_address, port)

            try:
                client = caldav.DAVClient(url)
                principal = client.principal()

                #Select calendar
                events = []
                for calendar in principal.calendars():
                    for event in calendar.events():
                        event_text = event.data
                        cal = vobject.readOne(event_text)
                        event_date = cal.vevent.dtstart.value.date()
                        #If in date, append.
                        if event_date == date:
                            event_dict = {"date":cal.vevent.dtstart.value.date(), "time":cal.vevent.dtstart.value.time(), "event": cal.vevent.summary.valueRepr()}
                            events.append(event_dict)
                return events

            except:
                self.speak_dialog("error.logging.in")
                return None

        elif server_type == None:
            #Get server info on home. Password in config.
            server_address = self.settings.get("server_address")
            calendar = self.settings.get("calendar")
            port = self.settings.get("port")
            account_config = self.config_core.get("calendar", {})
            username = account_config.get("username")
            password = account_config.get("password")

            url = "http://{}:{}@{}:{}/".format(username, password, server_address, port)

            try:
                client = caldav.DAVClient(url)
                principal = client.principal()

                #Select calendar
                events = []
                for calendar in principal.calendars():
                    for event in calendar.events():
                        event_text = event.data
                        cal = vobject.readOne(event_text)
                        event_date = cal.vevent.dtstart.value.date()
                        #If in date, append.
                        if event_date == date:
                            event_dict = {"date":cal.vevent.dtstart.value.date(), "time":cal.vevent.dtstart.value.time(), "event": cal.vevent.summary.valueRepr()}
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
        with open(filename, 'w') as data_file:
            f.writelines(data)
            return True


def create_skill():
    return Calendar()

