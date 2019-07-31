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


import os, sys, re, requests, textwrap
import fire
from math import exp

from datetime import datetime, timedelta
from dateutil import parser
from pprint import pprint
from json import loads, dumps
from parameters.local_parameters import PATH, PLATES_FILE
from notify import send_to_slack

def calculate_angular_momentum(p):
    spins = p['spin_history']
    period = p['period_in_days']
    today = datetime.now().date()
    L = sum([ exp( -(today-datetime.strptime(date_i,"%Y-%m-%d").date()).days/period ) for date_i in spins])
    return L

def spins_in_range(p, start_date, end_date):
    # This function is kind of a superset of spins_in_span().
    count = 0
    for spin in p['spin_history']:
        if start_date <= parser.parse(spin).date() <= end_date:
            count += 1
    return count

def calculate_streak(p):
    spins = p['spin_history']
    period = p['period_in_days']
    end = datetime.now().date()
    streak = 0
    while spins_in_range(p, end - timedelta(days=period), end) > 0:
        streak += 1
        end -= timedelta(days=period)
    return streak

def print_table(ps):
    template = "{{:<11.11}}  {{:<30.30}}  {}  {{:<10.10}}  {} {{:>6}} {} {{:>6}}"
    fmt = template.format("{:>7.8}","{:<6}","{:<3}")
    print(fmt.format("", "", "Cycles", "", "Period", "", "", ""))
    print(fmt.format("Code","Description","late", "Last spun","in days", "Status", "L", "Streak"))
    print("============================================================================================")
    fmt = template.format("{:>7.1f}","{:<7.1f}","{:<3.1f}") # The first digit in the float formatting
    # strings has to be manually tweaked to make everything line up.
    for p in ps:
        if 'last_spun_dt' not in p or p['last_spun_dt'] is None:
            last_spun_date = None
        else:
            last_spun_date = datetime.strftime(p['last_spun_dt'],"%Y-%m-%d")
        if 'status' not in p or p['status'] is None:
            p['status'] = 'Active'
        print(fmt.format(p['code'],p['description'],
            p['cycles_late'], last_spun_date,
            p['period_in_days'],p['status'],
            p['angular_momentum'],
            p['streak']))
    print("============================================================================================\n")

#plates = {"trash": {"period_in_days": 3, "last_spun": "2017-10-22T22:40:06.500726", "description": "Put out the trash." }, "pi": {"period_in_days": 60, "last_spun": "2016-10-22T22:40:06.500726", "description": "Make cool thing for Raspberry Pi." } }
#plates = [{"code": "trash", "period_in_days": 7, "last_spun": "2017-10-22T22:40:06.500726", "description": "Put out the trash." }, {"code": "pi", "period_in_days": 60, "last_spun": "2016-10-22T22:40:06.500726", "description": "Make cool thing for Raspberry Pi." } ]
#pprint(plates)
#with open(PATH+"/plates.json",'w') as f:
#    f.write(dumps(plates, indent=4))

def find_all_racks():
    from os import listdir
    from os.path import isfile, join
    import re
    onlyfiles = [f for f in listdir(PATH) if isfile(join(PATH, f))]
    return [re.sub("\.json","",f) for f in onlyfiles if re.search("json$",f)]

def is_spinning(plate):
    return 'status' not in plate or plate['status'] == 'Active'

def last_spun_dt(plate):
    if plate['last_spun'] is None:
        last_spun = None
    else:
        last_spun = datetime.strptime(plate['last_spun'],"%Y-%m-%dT%H:%M:%S.%f")
    return last_spun

def inspect(plates):
    wobbly_plates = []
    for i,plate in enumerate(plates):
        plate['angular_momentum'] = calculate_angular_momentum(plate)
        plate['streak'] = calculate_streak(plate)
        if is_spinning(plate):
            period_in_days = timedelta(days = plate['period_in_days']) 
            last_spun = last_spun_dt(plate)
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

def intersection(start1,end1,start2,end2):
    start = max(start1,start2)
    end = min(end1,end2)
    diff = end - start
    if diff < timedelta(days = 0):
        diff = timedelta(days = 0)
    return diff

def is_more_in(start,span,ranges):
    """Determine whether a given time span (from start to start+span)
    is more in the periods represented by ranges (where ranges
    has the form [(begin1,end1),(begin2,end2),...(beginN,None)]."""

    cumulative = timedelta(days=0)

    end = start + span
    if end > datetime.now():
        end = datetime.now()

    for r in ranges:

        r_start_dt = datetime.strptime(r[0],"%Y-%m-%d")
        if r[1] is None:
            r_end_dt = datetime.now()
        else:
            r_end_dt = datetime.strptime(r[1],"%Y-%m-%d")
        cumulative += intersection(start,end,r_start_dt,r_end_dt)
    return cumulative + cumulative > end - start

def spins_in_span(spin_history,span):
    now = datetime.now()
    start = now - span
    in_span = [s for s in spin_history if start <= datetime.strptime(s,"%Y-%m-%d") <= now]
    return len(in_span)

def form_bar(p,start_dt,end_dt,terminator):
    unit = timedelta(days = 7)
    fmt = "{:<11.11} {:>3}  {:>3} {:<}{}"
    duration = int((end_dt - start_dt).days/7.0) # in weeks
    #duration_less_one = duration-1 if duration > 0 else 0
    #d_bar = '|' * duration_less_one
    pauses = load_pauses(p)
    d = start_dt
    d_bar = ''
    while d < end_dt:
        if is_more_in(d,unit,pauses):
            d_bar += '"'
        else:
            d_bar += '|'
        d += unit

    if len(d_bar) > 0:
        d_bar = d_bar[:-1]
    n = 2
    span = timedelta(n*p['period_in_days'])
    if p['spin_history'] is not None:
        spin_history = p['spin_history'] # A list of date_strings
    else:
        spin_history = []
    in_last_n_cycles = spins_in_span(spin_history,span)

    bar = fmt.format(p['code'], in_last_n_cycles, duration, d_bar, terminator)
    return bar

def load_pauses(p):
    if 'pauses' in p:
        pauses = p['pauses'] # A list of 2-element lists, with the first element being the
        # beginning of the pause and the second being the end of the pause (equal to None) if
        # the pause is ongoing.
    else:
        pauses = []
    return pauses

def prompt_for(input_field):
    try:
        text = raw_input(input_field+": ")  # Python 2
    except:
        text = input(input_field+": ")  # Python 3
    return text

def prompt_to_edit_field(d, base_prompt, field):
    new_value = prompt_for('{} ({})'.format(base_prompt, d[field]))
    if new_value == '':
        return d[field]
    else:
        return new_value

class Plates(object):
    """A collection of plates/projects, with all the functions that one might want to call
    from the command line through fire as part of the Plates object."""

    def __init__(self, plates_file=PLATES_FILE):
        self._filepath = PATH+"/"+plates_file

    def __str__(self):
        return self._filepath

    def load(self):
        #plates_filepath = PATH+"/"+PLATES_FILE
        plates_filepath = self._filepath
        if os.path.exists(plates_filepath):
            with open(plates_filepath,'r') as f:
                plates = loads(f.read())
            return plates
        else:
            return []

    def store(self,plates):
        with open(self._filepath,'w') as f:
            f.write(dumps(plates, indent=4))

    def check(self,show_all=False):
        plates = self.load()
        wobbly_plates = inspect(plates)
        if show_all:
            all_plates_with_lateness = wobbly_plates
            for p in plates:
                if p['code'] not in [q['code'] for q in all_plates_with_lateness]:
                    p['cycles_late'] = 0
                    p['last_spun_dt'] = last_spun_dt(p)
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

    def all(self):
        self.check(show_all=True)

    def view(self,code=None):
        plates = self.load()
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

    def add(self,code=None):
        plates = self.load()
        d = {'code': code}
        if code is None:
            d['code'] = str(prompt_for('Code'))
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
        self.store(plates)
        print('"{}" was added to the plates being tracked.'.format(d['description']))
        self.check()

    def edit(self,code=None):
        plates = self.load()
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

        # [ ] What about editing the spin history?
        self.store(plates)
        print('"{}" has been edited.'.format(p['description']))
        self.check()

    def spin(self,code=None,days_ago=None):
        plates = self.load()
        if code is None:
            code = prompt_for('Code')
        codes = [p['code'] for p in plates]
        if code not in codes:
            # Try matching by partial substring
            partial_matches = [c for c in codes if re.match(str(code),c) is not None]
            if len(partial_matches) == 1:
                code = partial_matches[0]
                print("Spinning {}.".format(code))
            else:
                print("There's no plate under that code. Try \n     > spin add {}".format(code))
                return
        else:
            print("Spinning {}.".format(code))

        # Find the corresponding plate to spin.
        index = codes.index(code)
        p = plates[index]
        
        if days_ago is None:
            dt_spun = datetime.now()
        else:
            dt_spun = datetime.now() - timedelta(days=int(days_ago))

        date_spun = datetime.strftime(dt_spun,"%Y-%m-%d")

        if 'spin_history' in p:
            # Load spin history from file.
            if p['spin_history'] is None:
                spin_history = []
            else:
                spin_history = p['spin_history']
            if spin_history == [] and p['last_spun'] is not None:
                last_spun_dt = datetime.strptime(p['last_spun'], "%Y-%m-%dT%H:%M:%S.%f")
                last_spun_string = datetime.strftime(last_spun_dt,"%Y-%m-%d")
                spin_history = [last_spun_string,date_spun]
            else:
                spin_history.append(date_spun)
            p['spin_history'] = spin_history
        elif p['last_spun'] is not None:
            last_spun_dt = datetime.strptime(p['last_spun'], "%Y-%m-%dT%H:%M:%S.%f")
            last_spun_string = datetime.strftime(last_spun_dt,"%Y-%m-%d")
            spin_history = [last_spun_string,date_spun]
            p['spin_history'] = spin_history
        else:
            p['spin_history'] = [date_spun]
        p['last_spun'] = datetime.strftime(dt_spun,"%Y-%m-%dT%H:%M:%S.%f")

        self.store(plates)

    def shelve(self,code=None,shelving_mode='Done'):
        # shelving_mode allows for a plate to be paused, but
        # this is not being taken into account in its spin stats
        # calculations yet.
        plates = self.load()
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

        previous_status = str(p['status']) if 'status' in p else 'Active'
        if shelving_mode == previous_status:
            print('The plate ("{}") is already shelved with status {}.'.format(p['code'],previous_status))
            return

        if shelving_mode == 'Paused':
            pauses = load_pauses(p)
            pauses.append([today, None])
            p['pauses'] = pauses
        elif shelving_mode == 'Active' and previous_status == 'Paused':
            pauses = load_pauses(p)
            if len(pauses) == 0:
                print("Inferring missing pause history...")
                pauses = [[p['spin_history'],today]]
            else:
                assert pauses[-1][1] == None
                pauses[-1][1] = today
            p['pauses'] = pauses
        #else: # Maybe deal with cases where projects are reawakened (Done ==> Active, Done ==> Paused),
        # though Done ==> Paused will already be handled by the first if statement above.

        p['status'] = shelving_mode
        self.store(plates)
        print('Put the {} plate ("{}") on the shelf with mode {}.'.format(p['code'],p['description'], shelving_mode))

    def pause(self,code=None):
        self.shelve(code,shelving_mode='Paused')

    def unpause(self,code=None):
        self.shelve(code,shelving_mode='Active')

    def done(self,code=None):
        self.shelve(code,shelving_mode='Done')

    def stats(self):
        plates = self.load()
        template = "{{:<11.11}}  {{:<30.30}} {{:<8}}  {}  {{:<7}} {{:<6}}"
        fmt = template.format("{:>9.9}")
        print(fmt.format("", "", "Total", "Effective", "Period", ""))
        print(fmt.format("Code","Description","spins", "period","in days", "Status"))
        print("=============================================================================")
        for p in plates:
            total_spins = 0
            in_last_n_cycles = 0
            effective_period = ""
            fmt = template.format("{:9}")
            if 'spin_history' in p:
                if p['spin_history'] is not None:
                    spin_history = p['spin_history'] # A list of date_strings
                else:
                    spin_history = []
                total_spins = len(spin_history)
                n = 2
                span = timedelta(n*p['period_in_days'])
                in_last_n_cycles = spins_in_span(spin_history,span)
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
                "{:<} ({})".format(total_spins, in_last_n_cycles),
                effective_period,
                p['period_in_days'],
                p['status']))
        print("=============================================================================\n")

    ##### PROJECT-VIEW FUNCTIONS #####

    def projects(self, full=False):
        """Show a project view (rather than a communications-oriented spin view)
        by using a bar chart, the first spin date, the current date, and whether
        the project is still active."""
        ps = self.load()
        ender = {'Active': '>', 'Done': ']', 'Paused': '"'}
        scorer = {'Active': 0, 'Paused': 1, 'Done': 2}
        bars = []
        index = []
        scores = {}
        for k,project in enumerate(ps):
            if 'spin_history' in project and len(project['spin_history']) > 0:
                start = project['spin_history'][0] # e.g., "2018-02-02"
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                if 'status' not in project:
                    status = 'Active'
                else:
                    status = project['status']
                if status in ['Active']:
                    end_dt = datetime.now()
                else:
                    end = project['spin_history'][-1] # e.g., "2018-10-10"
                    end_dt = datetime.strptime(end, "%Y-%m-%d")
                if full and status == 'Paused':
                    end_dt = datetime.now() # This forces even paused projects to print
                    # full bar charts.

                # [ ] Once a paused project is unpaused, it will make sense to
                # exclude the paused weeks from the non-full bar chart.
                terminator = ender[status]
                score = scorer[status]
                bar = form_bar(project,start_dt,end_dt,terminator)
                bars.append(bar)
                index.append(k)
                scores[bar] = score

        sorted_bars = sorted(bars,key = lambda b: scores[b])

        header = """           spins in
           last 2   project
code       cycles   duration"""
        print(header)
        for k,bar in zip(index,sorted_bars):
            print(bar)

        return sorted_bars, header

    def p(self,full=False):
        """A short alias to produce the project-view output."""
        self.projects(full)

    def p_watch(self):
        bars, header = self.projects()
        msg = '\n'.join(bars)
        send_to_slack(msg,username='Captain Projecto',channel='@david',icon=':film_projector:')

    ##### END PROJECT-VIEW FUNCTIONS #####

if __name__ == '__main__':
    if len(sys.argv) == 1:
        Plates().check() # Make this the default.
    else:
        all_racks = find_all_racks()
        arg1 = sys.argv[1]
        if arg1 in all_racks: # If the first argument designates 
            plates_file = "{}.json".format(arg1) # one of the plates
            del(sys.argv[1]) # peel it off, and use it to override the
            fire.Fire(Plates(plates_file=plates_file)) # default plates file.
        else:
            fire.Fire(Plates())
