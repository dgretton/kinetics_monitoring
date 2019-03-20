import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime
#from easygui import msgbox # I think this doens't work on mac?
import pdb
import sys, os
import math
import csv

number_of_turb = 96

def name_well_96(x):
    column = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    #return column[x%8-1]+'%02d' % int(math.floor((x-1)/8)+1)
    return column[x%8-1]+ str(int(math.floor((x-1)/8)+1))       # Danger: database wells are not all three characters

def line_property(ln):
    try:
        return ln.split(':')[1].strip()
    except IndexError:
        print('you need to have colons in your config lines')
        exit()
with open('params.cfg') as f:
    paramlist = list(f.readlines())
def propty(name):
    for line in paramlist:
        if name.lower() in line.lower():
            return line_property(line)
    else:
        print('property "' + name + '" not found')
        raise ValueError()

try:
    db_name = sys.argv[1]
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    c.execute('select count(distinct plate_id) from measurements')
    num_plates, = c.fetchone()
    c.execute('select distinct data_type from measurements')
    protocols = [p for p, in c.fetchall()]
except IndexError:
    try:
        db_name = propty('database')
        num_plates = int(propty('plates'))
        protocols = [s.strip() for s in propty('protocols').split(',')]
        print('\nUSING PARAMETERS FROM PARAMS.CFG, hopefully that\'s what '
            'you want.\n(if not, specify with first argument, e.g. below)\n\n\t'
            'python plot_from_database.py mydatabasename.db\n')
        conn = sqlite3.connect(db_name)
        c = conn.cursor()
    except Exception:
        print('Could not get database from params.cfg, edit that file or specify database '
            'with first argument, e.g.\n\npython plot_from_database.py mydatabasename.db)\n')
        exit()

print('\n** Database: ' + db_name + ' **\n')

for plate in range(1, num_plates+1):
    for type in protocols:
        
        print("Processing plate", plate, "type", type)
        
        # collect csv data to file
        csv_data = [] 
        
        scale = 1
        fig1 = plt.figure(figsize=(24*scale, 16*scale))
        subplot = 0
        for row in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
            for column in range(1, 12+1):
                well = row+str(column)
                subplot = subplot + 1
                # set up plot
                ax = fig1.add_subplot(8, number_of_turb/8, subplot)
                ax.set_title("Well" + well, x=0.5, y=0.8)
        
                n = ('reader_plate_' + str(plate), well, type, )
                c.execute('SELECT filename, well, reading FROM measurements WHERE plate_id=? AND well=? AND data_type=?', n)
                readings_list = c.fetchall()
                if len(readings_list) == 0:
                    conn.close()
                    exit()
                vals = [(datetime.strptime(f[-15:-4], '%y%m%d_%H%M'), w, v) for (f, w, v) in readings_list]
                vals = [(t, w, v) for t, w, v in vals if t > datetime(2018, 11, 7, 21, 15)] 
                
                # plot
                plt.plot([j for (j, _, _) in vals], [lum for (j, _, lum) in vals], 'b.')
    
                # common axis limits for all subplots
                if 'abs' in type:
                    plt.ylim(0.0, 1.0)
                else:
                    plt.ylim(0.0, 100000.0)
                
                # decrease number of plotted X axis labels
                # make there be fewer labels so that you can read them
                times = [x for (x, _, _) in vals]
                deltas = [t - times[0] for t in times]
                labels = [int(d.seconds/60/60 + d.days*24) for d in deltas]
                labels_sparse = [labels[x] if x % 12 == 0 else '' for x in range(len(labels))]
                plt.xticks(times, labels_sparse)
                locs, labels = plt.xticks()
                
                # collect csv data
                if(well == 'A1'):
                   csv_data.append(['Time'] + [t for (t, _, _) in vals])
                correct_well_name = well[0]+str(well[1:]).zfill(2) # three characters
                csv_data.append([correct_well_name] + [v for (_, _, v) in vals])
        print(len(readings_list), "entries fetched")
    
        fig1.tight_layout()
        plt.savefig(os.path.join('graphs', db_name[:-3]+'_plate' + str(plate) + "_" + type + ".png"), dpi = 200)
        plt.close(fig1)
        
        # write data to a file
        csvfile = open(os.path.join('excel', db_name[:-3]+'_reader_plate_' + str(plate)+"_"+type+'.csv'), 'w')
        csvwriter = csv.writer(csvfile)
        for d in csv_data:
            csvwriter.writerow(d)    
        csvfile.close()  

# We can also close the connection if we are done with it.
# Just be sure any changes have been committed or they will be lost.
conn.close()


