## To open the images on PC use in the terminal not the ssh:
scp pi@192.168.1.105:~/motion_snapshots/*.jpg .

## To delete older files on the sd:
find ~/motion_snapshots/ -name "*.jpg" -mtime +7 -print -delete

## To open the python script use:
nano stream.py

Set this up to run automatically so you never have to think about it (e.g. auto-delete anything older than 7 days, once a day):

bash
crontab -e

If it asks which editor, pick nano (usually option 1). Add this line at the bottom:

0 3 * * * find /home/pi/motion_snapshots/ -name "*.jpg" -mtime +7 -delete

Save and exit (Ctrl+O, Enter, Ctrl+X). This runs every day at 3 AM and clears anything older than a week, so the SD card never fills up unattended.

Want the automatic cleanup set up the same way on your other three Pis too, or just deal with test for now?
