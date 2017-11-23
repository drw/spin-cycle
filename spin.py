# This script remembers the last time a particular task was done
# and its desired periodicity and shows tasks when they need to be
# done again.

# Much of the initial approach for this command-line tool was 
# taken from pocket-watch/glance.py.

# Usage:
# > spin
#                                                                 Period
# Code        Description                Cycles late  Last spun   in days
# =========================================================================
# trash       Put out the trash.               9.544  2017-10-22  3
#
# > spin trash
# "Put out the trash" has been spun as of 0.3 seconds ago. Nice job!
#
# > spin add pi


import requests, textwrap

from datetime import datetime, timedelta
from pprint import pprint
from json import loads, dumps
from parameters.local_parameters import PATH

def print_table(ps):
    template = "{{:<10.10}}  {{:<20.20}}  {}  {{:<10.10}}  {{:<12}}"
    fmt = template.format("{:>16.20}")
    print(fmt.format("", "", "", "", "Period"))
    print(fmt.format("Code","Description","Cycles late", "Last spun","in days"))
    print("=========================================================================")
    #fmt = "{:<33.33} {:<20.3f} {:<10.10} {:<12.12}"
    fmt = template.format("{:>16.3f}")
    for p in ps:
        last_spun_date = datetime.strftime(p['last_spun_dt'],"%Y-%m-%d")
        print(fmt.format(p['code'],p['description'],
            p['cycles_late'], last_spun_date,
            p['period_in_days']))
    print("=========================================================================\n")

#plates = {"trash": {"period_in_days": 3, "last_spun": "2017-10-22T22:40:06.500726", "description": "Put out the trash." }, "pi": {"period_in_days": 60, "last_spun": "2016-10-22T22:40:06.500726", "description": "Make cool thing for Raspberry Pi." } }
#plates = [{"code": "trash", "period_in_days": 7, "last_spun": "2017-10-22T22:40:06.500726", "description": "Put out the trash." }, {"code": "pi", "period_in_days": 60, "last_spun": "2016-10-22T22:40:06.500726", "description": "Make cool thing for Raspberry Pi." } ]
#pprint(plates)
#with open(PATH+"/plates.json",'w') as f:
#    f.write(dumps(plates, indent=4))

with open(PATH+"/plates.json",'r') as f:
#    pprint(f.read())
    plates = loads(f.read())

period = {'Annually': timedelta(days = 366),
        'Bi-Annually': timedelta(days = 183),
        'Quarterly': timedelta(days = 31+30+31),
        'Monthly': timedelta(days = 31),
        'Bi-Monthly': timedelta(days = 16),
        'Weekly': timedelta(days = 7),
        'Bi-Weekly': timedelta(days = 4),
        'Daily': timedelta(days = 1),
        'Hourly': timedelta(hours = 1),
        'Multiple Times per Hour': timedelta(minutes=30)}

wobbly_plates = []
for i,plate in enumerate(plates):
    last_spun = datetime.strptime(plate['last_spun'],"%Y-%m-%dT%H:%M:%S.%f") 
    period_in_days = timedelta(days = plate['period_in_days']) 
    if last_spun + period_in_days < datetime.now():
        print("{} is overdue.".format(plate["code"]))
        wobbler = dict(plate)
        wobbler['last_spun_dt'] = last_spun
        lateness = datetime.now() - (last_spun + period_in_days)
        wobbler['cycles_late'] = lateness.total_seconds()/period_in_days.total_seconds()
        wobbly_plates.append(wobbler)

wobbly_ps_sorted = sorted(wobbly_plates, 
                        key=lambda u: -u['cycles_late'])
print("\nPlates by Wobbliness: ")
print_table(wobbly_ps_sorted)

wobbly_ps_by_recency = sorted(wobbly_plates, 
                        key=lambda u: u['last_spun'])
print("\n\nWobbly Plates by Date of Last Spinning: ")
print_table(wobbly_ps_by_recency)


coda = "Out of {} plates, {} need to be spun.".format(len(plates),len(wobbly_plates))
print(textwrap.fill(coda,70))
