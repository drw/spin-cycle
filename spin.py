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


import os, sys, requests, textwrap
import fire

from datetime import datetime, timedelta
from pprint import pprint
from json import loads, dumps
from parameters.local_parameters import PATH

def print_table(ps):
    template = "{{:<11.11}}  {{:<30.30}}  {}  {{:<10.10}}  {{:<6}} {{:<6}}"
    fmt = template.format("{:>7.9}")
    print(fmt.format("", "", "Cycles", "", "Period", ""))
    print(fmt.format("Code","Description","late", "Last spun","in days", "Status"))
    print("================================================================================")
    fmt = template.format("{:>7.1f}")
    for p in ps:
        if 'last_spun_dt' not in p or p['last_spun_dt'] is None:
            last_spun_date = None
        else:
            last_spun_date = datetime.strftime(p['last_spun_dt'],"%Y-%m-%d")
        if 'status' not in p or p['status'] is None:
            p['status'] = 'Active'
        print(fmt.format(p['code'],p['description'],
            p['cycles_late'], last_spun_date,
            p['period_in_days'],p['status']))
    print("================================================================================\n")

#plates = {"trash": {"period_in_days": 3, "last_spun": "2017-10-22T22:40:06.500726", "description": "Put out the trash." }, "pi": {"period_in_days": 60, "last_spun": "2016-10-22T22:40:06.500726", "description": "Make cool thing for Raspberry Pi." } }
#plates = [{"code": "trash", "period_in_days": 7, "last_spun": "2017-10-22T22:40:06.500726", "description": "Put out the trash." }, {"code": "pi", "period_in_days": 60, "last_spun": "2016-10-22T22:40:06.500726", "description": "Make cool thing for Raspberry Pi." } ]
#pprint(plates)
#with open(PATH+"/plates.json",'w') as f:
#    f.write(dumps(plates, indent=4))

def load():
    plates_filepath = PATH+"/plates.json"
    if os.path.exists(plates_filepath):
        with open(plates_filepath,'r') as f:
        #    pprint(f.read())
            plates = loads(f.read())
        return plates
    else:
        return []

def store(plates):
    with open(PATH+"/plates.json",'w') as f:
        f.write(dumps(plates, indent=4))

def is_spinning(plate):
    return 'status' not in plate or plate['status'] == 'Active'

def inspect(plates):
    wobbly_plates = []
    for i,plate in enumerate(plates):
        if is_spinning(plate):
            if plate['last_spun'] is None:
                last_spun = None
            else:
                last_spun = datetime.strptime(plate['last_spun'],"%Y-%m-%dT%H:%M:%S.%f") 
            period_in_days = timedelta(days = plate['period_in_days']) 
            if last_spun is None or last_spun + period_in_days < datetime.now():
                print("{} is overdue.".format(plate["code"]))
                wobbler = dict(plate)
                wobbler['last_spun_dt'] = last_spun
                if last_spun is None:
                    wobbler['cycles_late'] = 0
                else:
                    lateness = datetime.now() - (last_spun + period_in_days)
                    wobbler['cycles_late'] = lateness.total_seconds()/period_in_days.total_seconds()
                wobbly_plates.append(wobbler)
    return wobbly_plates

def stats():
    plates = load()
    template = "{{:<11.11}}  {{:<30.30}} {{:<6}}  {}  {{:<6}} {{:<6}}"
    fmt = template.format("{:>9.9}")
    print(fmt.format("", "", "Total", "Effective", "Period", ""))
    print(fmt.format("Code","Description","spins", "period","in days", "Status"))
    print("=============================================================================")
    for p in plates:
        total_spins = 0
        effective_period = ""
        fmt = template.format("{:9}")
        if 'spin_history' in p:
            if p['spin_history'] is not None:
                spin_history = p['spin_history'] # A list of date_strings
            else:
                spin_history = []
            total_spins = len(spin_history)
            if total_spins > 0:
                first_date = datetime.strptime(spin_history[0],'%Y-%m-%d')
                last_date = datetime.strptime(spin_history[-1],'%Y-%m-%d')
                if total_spins in [0,1]:
                    effective_period = "None"
                else:
                    effective_period = (last_date-first_date).days/(total_spins-1.0)
                    fmt = template.format("{:>9.1f}")
        if 'status' not in p or p['status'] is None:
            p['status'] = 'Active'
        print(fmt.format(p['code'],p['description'],
            total_spins, 
            effective_period,
            p['period_in_days'],
            p['status']))
    print("=============================================================================\n")

def check(show_all=False):
    plates = load()
    wobbly_plates = inspect(plates)
    if show_all:
        all_plates_with_lateness = wobbly_plates
        for p in plates:
            if p['code'] not in [q['code'] for q in all_plates_with_lateness]:
                p['cycles_late'] = 0
                all_plates_with_lateness.append(p)
        wobbly_plates = all_plates_with_lateness

    wobbly_ps_sorted = sorted(wobbly_plates, 
                            key=lambda u: -u['cycles_late'])
    print("\nPlates by Wobbliness: ")
    print_table(wobbly_ps_sorted)

    wobbly_ps_by_recency = sorted(wobbly_plates, 
                            key=lambda u: u['last_spun'])
    print("\n\nWobbly Plates by Date of Last Spinning: ")
    print_table(wobbly_ps_by_recency)


    coda = "Out of {} plates, {} need{} to be spun.".format(len(plates), len(wobbly_plates), "s" if len(wobbly_plates) == 1 else "")
    print(textwrap.fill(coda,70))

def all():
    check(show_all=True)

def shelve(code=None):
    plates = load()
    if code is None:
        code = prompt_for('Code')
    codes = [p['code'] for p in plates]
    if code not in codes:
        print("There's no plate under that code. Try \n     > spin add {}".format(code))
        return

    # Find the corresponding plate to spin.
    index = codes.index(code)
    p = plates[index]

    today = datetime.strftime(datetime.now(),"%Y-%m-%d")
    p['status'] = 'Done'
    store(plates)
    print('Put the {} plate ("{}") on the shelf.'.format(p['code'],p['description']))

def spin(code=None):
    plates = load()
    if code is None:
        code = prompt_for('Code')
    codes = [p['code'] for p in plates]
    if code not in codes:
        print("There's no plate under that code. Try \n     > spin add {}".format(code))
        return

    # Find the corresponding plate to spin.
    index = codes.index(code)
    p = plates[index]

    today = datetime.strftime(datetime.now(),"%Y-%m-%d")
    if 'spin_history' in p:
        # Load spin history from file.
        if p['spin_history'] is None:
            spin_history = []
        else:
            spin_history = p['spin_history']
        if spin_history == [] and p['last_spun'] is not None:
            last_spun_dt = datetime.strptime(p['last_spun'], "%Y-%m-%dT%H:%M:%S.%f")
            last_spun_string = datetime.strftime(last_spun_dt,"%Y-%m-%d")
            spin_history = [last_spun_string,today]
        else: 
            spin_history.append(today)
        p['spin_history'] = spin_history
    elif p['last_spun'] is not None:
        last_spun_dt = datetime.strptime(p['last_spun'], "%Y-%m-%dT%H:%M:%S.%f")
        last_spun_string = datetime.strftime(last_spun_dt,"%Y-%m-%d")
        spin_history = [last_spun_string,today]
        p['spin_history'] = spin_history
    else: 
        p['spin_history'] = [today]
    p['last_spun'] = datetime.strftime(datetime.now(),"%Y-%m-%dT%H:%M:%S.%f")

    store(plates)

def prompt_for(input_field):
    try:
        text = raw_input(input_field+": ")  # Python 2
    except:
        text = input(input_field+": ")  # Python 3
    return text

def add(code=None):
    plates = load()
    d = {'code': code}
    if code is None:
        d['code'] = prompt_for('Code')
    if d['code'] in [p['code'] for p in plates]:
        print("There's already a plate under that code. Try \n     > spin edit {}".format(d['code']))
        return

    d['description'] = prompt_for('Description')
    d['period_in_days'] = float(prompt_for('Period in days'))
    last_spun = prompt_for("Last spun [YYYY-MM-DD | Enter for now | 'None' for never]")
    if last_spun == 'None':
        d['last_spun'] = None
        d['spin_history'] = []
    elif last_spun == '':
        d['last_spun'] = datetime.strftime(datetime.now(),"%Y-%m-%dT%H:%M:%S.%f")
        d['spin_history'] = [datetime.strftime(datetime.now(),"%Y-%m-%d")]
    else:
        d['last_spun'] = datetime.strftime(datetime.strptime(last_spun,"%Y-%m-%d"), "%Y-%m-%dT%H:%M:%S.%f")
        d['spin_history'] = [datetime.strftime(datetime.strptime(last_spun,"%Y-%m-%d"), "%Y-%m-%d")]
        # The above line seems like it does something and then undoes it, but really it's 
        # validating that the entered date is in the right format.

    plates.append(d)
    store(plates)
    print('"{}" was added to the plates being tracked.'.format(d['description']))
    check()

def prompt_to_edit_field(d, base_prompt, field):
    new_value = prompt_for('{} ({})'.format(base_prompt, d[field]))
    if new_value == '':
        return d[field]
    else:
        return new_value

def view(code=None):
    plates = load()
    if code is None:
        print("You have to specify the code of an existing plate to view.")
        print("Here are the current plates: {}\n".format(', '.join([p['code'] for p in plates])))
        code = prompt_for('Enter the code')
    codes = [p['code'] for p in plates]
    while code not in codes:
        print("There's no plate under that code. Try again.")
        print("Here are the current plates: {}\n".format(', '.join([p['code'] for p in plates])))
        code = prompt_for('Enter the code of the plate you want to edit')

    index = codes.index(code)
    p = plates[index]
    pprint(p)

def edit(code=None):
    plates = load()
    if code is None:
        print("You have to specify the code of an existing plate to edit.")
        print("Here are the current plates: {}\n".format(', '.join([p['code'] for p in plates])))
        code = prompt_for('Enter the code')
    codes = [p['code'] for p in plates]
    while code not in codes:
        print("There's no plate under that code. Try again.")
        print("Here are the current plates: {}\n".format(', '.join([p['code'] for p in plates])))
        code = prompt_for('Enter the code of the plate you want to edit')

    index = codes.index(code)
    p = plates[index]
    p['description'] = prompt_to_edit_field(p,'Description','description')
    p['period_in_days'] = float(prompt_to_edit_field(p,'Period in days','period_in_days'))

    base_prompt = "Last spun [YYYY-MM-DD | 'now' | 'None' for never]"
    field = 'last_spun'
    last_spun = prompt_for('{} ({})'.format(base_prompt, p[field]))
    if last_spun != '':
        if last_spun == 'None':
            p['last_spun'] = None
        elif last_spun == 'now':
            p['last_spun'] = datetime.strftime(datetime.now(),"%Y-%m-%dT%H:%M:%S.%f")
        else:
            p['last_spun'] = datetime.strftime(datetime.strptime(last_spun,"%Y-%m-%d"), "%Y-%m-%dT%H:%M:%S.%f")
    # plates has now been updated since p points to the corresponding element in plates.
    store(plates)
    print('"{}" has been edited.'.format(p['description']))
    check()

if __name__ == '__main__':
    if len(sys.argv) == 1:
        check() # Make this the default.
    else:
        fire.Fire()
