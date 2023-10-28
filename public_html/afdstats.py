#! /usr/bin/python
# -*- coding: utf-8 -*-

import cgitb; cgitb.enable()

import MySQLdb
import sys
import os
import traceback
import cgi
import urllib
import re
import datetime
import time
import htmllib

MAXLIMIT = 500

#TODO: Provide link to usersearch.py that will show all AfD edits during the time period that this search covers


matchstats = [0,0,0]	#matches, non-matches, no consensus

#initialize stats variable
stats = {}
statsresults = ["k", "d", "sk", "sd", "m", "r", "t", "u", "nc"]
votetypes = ["Keep", "Delete", "Speedy Keep", "Speedy Delete", "Merge", "Redirect", "Transwiki", "Userfy"]
statsvotes = statsresults[:-1]
for v in statsvotes:
	for r in statsresults:
		stats[v+r] = 0
for v in votetypes:
	stats[v] = 0

FOOTER = '<footer>Bugs, suggestions, questions?  Contact the maintainers at <a href="http://en.wikipedia.org/wiki/User_talk:Enterprisey">User talk:Enterprisey</a> and <a href="http://en.wikipedia.org/wiki/User_talk:Σ">User talk:Σ</a> • <a href="https://github.com/enterprisey/afdstats" title="afdstats on GitHub">Source code</a></footer>'

def main():
	global MAXLIMIT
	global matchstats
	global stats
	global statsresults
	global votetypes
	global statsvotes

	starttime = time.time()
	
	print "Content-Type: text/html"
	print
	print """<!doctype html>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
<title>AfD Stats - Results</title>
<link rel="stylesheet" type="text/css" href="afdstats.css">
</head>
<body>
<div style="width:875px;">"""
	try:
                ##################Validate input
		form = cgi.FieldStorage()
		if "name" not in form:
			errorout("No username entered.")
		username = form["name"].value.replace("_", " ").replace("+", " ").strip()
		username = urllib.unquote(username)
		username = username[0].capitalize() + username[1:]
		
		maxsearch = 200
		if "max" in form:
			try:
				maxsearch = min(MAXLIMIT, int(form["max"].value))
			except:
				maxsearch = 200
				
		if "startdate" in form:
			startdate = str(form["startdate"].value)
		else:
			startdate = ""
			
		nomsonly = False
		if "nomsonly" in form:
			if form["nomsonly"].value.lower() in ["1", "true", "yes"]:
				nomsonly = True
				
		if "altname" in form:
			altusername = urllib.unquote(form.getvalue("altname").strip())
		else:
                        altusername = ""

		##################Query database
		db = MySQLdb.connect(db='enwiki_p', host="enwiki.labsdb", read_default_file=os.path.expanduser("~/replica.my.cnf"))
		cursor = db.cursor()
		
		try:
			if len(startdate)==8 and int(startdate)>20000000 and int(startdate)<20300000:
				startdatestr = " AND rev_timestamp<=" + startdate + "235959"
			else:
				startdatestr = ""
		except:
			startdatestr = ""
		
		if nomsonly:
			cursor.execute(u'SELECT page_title FROM revision_userindex JOIN page ON rev_page=page_id JOIN actor ON actor_id=rev_actor WHERE actor_name=%s AND page_namespace=4 AND page_title LIKE "Articles_for_deletion%%" AND NOT page_title LIKE "Articles_for_deletion/Log/%%" AND rev_parent_id=0' + startdatestr + ' ORDER BY rev_timestamp DESC;', (username,))
		else:
			cursor.execute(u'SELECT DISTINCT page_title FROM revision_userindex JOIN page ON rev_page=page_id JOIN actor ON actor_id=rev_actor WHERE actor_name=%s AND page_namespace=4 AND page_title LIKE "Articles_for_deletion%%" AND NOT page_title LIKE "Articles_for_deletion/Log/%%"' + startdatestr + ' ORDER BY rev_timestamp DESC;', (username,))
		results = cursor.fetchall()

		print "<a href='http://tools.wmflabs.org/afdstats/'><small>&larr;New search</small></a>"
		print "<h1>AfD Statistics for User:" + cgi.escape(username) + "</h1>"
		
		if len(results) == 0:
			errorout("No AfD's found. This user may not exist.  Note that if the user's username does not appear in the wikitext of their signature, you may need to specify an alternate name.")

		print "<p>These statistics were compiled by an automated process, and may contain errors or omissions due to the wide variety of styles with which people cast votes at AfD.  Any result fields which contain \"UNDETERMINED\" were not able to be parsed, and should be examined manually.</p>"
		print "<h2>Vote totals</h2>"
		
		if startdate:
			datestr = datetime.datetime.strptime(startdate, "%Y%m%d").strftime("%b %d %Y")
			print "Total number of unique AfD pages edited by " + username + " (from " + datestr + " and earlier): " + str(len(results)) + "<br />"
		else:
			print "Total number of unique AfD pages edited by " + username + ": " + str(len(results)) + "<br />"
			print "Analyzed the last " + str(min(maxsearch, len(results))) + " AfD pages edited by this user.<br />"
	
		##################Analyze results
		pages = results[:min(maxsearch, len(results))]
		if len(pages) <= 50:
			alldata = APIpagedata(pages)
		else:
			alldata = {}
			for i in range(0, len(pages), 50):
				newdata = APIpagedata(pages[i:min(i+50, len(pages))])
				alldata = dict(alldata.items() + newdata.items())
		
		tablelist = []
		novotes = 0
	
		for entry in pages:
			try:
				page = entry[0]

				# "data" means the full page text
				raw_data = alldata["Wikipedia:" + page.replace("_", " ")]
				data = unescape(raw_data.replace("\n", "\\n")).replace("\\n", "\n")
				data = re.sub("<(s|strike|del)>.*?</(s|strike|del)>", "", data, flags=re.IGNORECASE|re.DOTALL)

				# We don't want to include the closing statement while finding votes
				header_index = data.find("==")
				if header_index > -1:
					votes_data = data[header_index:]
				else:
					votes_data = data
				votes = re.findall("'{3}?.*?'{3}?.*?(?:(?:\{\{unsigned.*?\}\})|(?:class=\"autosigned\"))?(?:\[\[[Uu]ser.*?\]\].*?\(UTC\))", votes_data, flags=re.IGNORECASE)
				result = findresults(data[:max(header_index, data.find("(UTC)"))])
				dupvotes = []
				deletionreviews = findDRV(data[:header_index], page)
				def find_user_idx(vote):
					possible_min_user_idx = vote.rfind("[[User")
					return possible_min_user_idx if possible_min_user_idx >= 0 else vote.rfind("[[user")

				find_voter_match = lambda vote: re.match("\[\[User.*?:(.*?)(?:\||(?:\]\]))", vote[find_user_idx(vote):], flags=re.IGNORECASE)

				for vote in votes:
					try:
						votermatch = find_voter_match(vote)
						if votermatch == None:
							continue
						voter = votermatch.group(1).strip()

						# Sometimes, a "#top" will sneak in, so remove it
						if voter.endswith("#top"):
							voter = voter[:-4]
						if "dev" in form and form["dev"].value.lower() in ["1", "true", "yes"]:
							print("<pre>{}, {}, {}</pre>".format(page, voter, vote))
                        
						# Underscores are turned into spaces by MediaWiki title processing
						voter = voter.replace("_", " ")

						# Check if the vote was made by the user we're counting votes for
						if voter.lower() == username.lower() or voter.lower() == altusername.lower():
							votetype = parsevote(vote[3:vote.find("'", 3)])
							if votetype == None or votetype == "UNDETERMINED":
								continue
							timematch = re.search("(\d{2}:\d{2}, .*?) \(UTC\)", vote)
							if timematch == None:
								votetime = ""
							else:
								votetime = parsetime(timematch.group(1))
							dupvotes.append((page, votetype, votetime, result, 0, deletionreviews))
					except:
						continue
				if len(dupvotes) < 1:
					firsteditor = DBfirsteditor(page, cursor)
                                        if firsteditor[0].lower() == username.lower(): #user is nominator
                                                tablelist.append((page, "Delete", firsteditor[1], result, 1, deletionreviews))
                                                updatestats("Delete", result)
                                        else:
                                                novotes += 1
							
				elif len(dupvotes) > 1:
					ch = len(dupvotes) - 1
					tablelist.append(dupvotes[ch])
					updatestats(dupvotes[ch][1], dupvotes[ch][3])
				else:
					tablelist.append(dupvotes[0])
					updatestats(dupvotes[0][1], dupvotes[0][3])
			except:
				continue
		db.close()
		
		##################Print results tables
		totalvotes = 0
		for i in votetypes:
			totalvotes += stats[i]
		if totalvotes > 0:
			print "<ul>"
			for i in votetypes:
				print "<li>" + i + " votes: " + str(stats[i]) + " (" + str(round((100.0*stats[i]) / totalvotes, 1)) + "%)</li>"
			print "</ul>"
			if novotes:
                                print "The remaining " + str(novotes) + " pages had no discernible vote by this user."
			print "<br />"
			print """<h2>Voting matrix</h2>
<p>This table compares the user's votes to the way the AfD eventually closed. The only AfD's included in this matrix are those that have already closed, where both the vote and result could be reliably determined. Results are across the top, and the user's votes down the side.  Green cells indicate "matches", meaning that the user's vote matched (or closely resembled) the way the AfD eventually closed, whereas red cells indicate that the vote and the end result did not match.</p>
</div>
<table border=1 style="float:left;" class="matrix">
<thead>
<tr>
<th colspan=2 rowspan=2></th>
<th colspan=9>Results</th>
</tr>
<tr>
"""
			for i in statsresults:
				print "<th>" + i.upper() + "</th>"
			print "</tr>"
			print "</thead>\n<tbody>"
			print "<tr><th rowspan=9>Votes</th></tr>"
			for vv in statsvotes:
				print "<tr>\n<th>" + vv.upper() + "</th>"
				for rr in statsresults:
					print matrixmatch(vv, rr) + str(stats[vv+rr]) + "</td>"
				print "</tr>"
			print "</tbody>"
			print "</table>"
			print """<br><div style="float:left;padding:20px;">
<small>Abbreviation key:
<br>K = Keep
<br>D = Delete
<br>SK = Speedy Keep
<br>SD = Speedy Delete
<br>M = Merge
<br>R = Redirect
<br>T = Transwiki
<br>U = Userfy/Draftify
<br>NC = No Consensus</small></div>
<div style="clear:both;"></div><br><br>
<div style="width:875px;">"""
				
			printstr = "<h2>Individual AfD's</h2>\n"
			if len(tablelist) > 0 and tablelist[-1][2]:
				printstr += '<a href="afdstats.py?name=' + username.replace(" ", "_") + '&max=' + str(maxsearch) + '&startdate=' + datefmt(tablelist[-1][2]) + '&altname=' + altusername + '"><small>Next ' + str(maxsearch) + " AfD's &rarr;</small></a><br>"
			printstr += """</div>
<table>
<thead>
<tr>
<th scope="col">Page</th>
<th scope="col">Date</th>
<th scope="col">Vote</th>
<th scope="col">Result</th>
</tr>
</thead>
<tbody>\n"""
			
			for i in tablelist:
				printstr += "<tr>\n"
				printstr += "<td>" + link(i[0]) + "</td>\n"
				printstr += "<td>" + i[2] + "</td>\n"
				if i[4] == 1:
					printstr += "<td>" + i[1] + " (Nom)</td>\n"
				else:
					printstr += "<td>" + i[1] + "</td>\n"
				printstr += match(i[1], i[3], i[5]) + "\n"
				printstr += "</tr>\n"
			printstr += "</tbody>\n</table>\n"
			printstr += '<div style="width:875px;">\n<a href="afdstats.py?name=' + username.replace(" ", "_") + '&max=' + str(maxsearch) + '&startdate=' + datefmt(tablelist[-1][2]) + '&altname=' + altusername + '"><small>Next ' + str(maxsearch) + " AfD's &rarr;</small></a><br /><br />"
	
			total_votes = sum(matchstats)
			if total_votes > 0:
				print("Number of AfD's where vote matched result (green cells): {} ({:.1%})<br>".format(matchstats[0], float(matchstats[0])/total_votes))
				print("Number of AfD's where vote didn't match result (red cells): {} ({:.1%})<br>".format(matchstats[1], float(matchstats[1])/total_votes))
				print("Number of AfD's where result was \"No Consensus\" (yellow cells): {} ({:.1%})<br>\n".format(matchstats[2], float(matchstats[2])/total_votes))
				if total_votes != matchstats[2]:
					print("Without considering \"No Consensus\" results, <b>{:.1%} of AfD's were matches</b> and {:.1%} of AfD's were not.".format(float(matchstats[0])/(total_votes - matchstats[2]), float(matchstats[1])/(total_votes - matchstats[2])))
			print printstr
		else:
			print "<br /><br />No votes found."

		elapsed = str(round(time.time() - starttime, 2))
		print '<small>Elapsed time: ' + elapsed + ' seconds.</small><br />'
		print FOOTER
		print '<a href="http://tools.wmflabs.org/afdstats/"><small>&larr;New search</small></a>'
		print "</div></body>\n</html>"

	
	except SystemExit:
		sys.exit(0)
	except:
		print sys.exc_info()[0]
		print "<br>"
		print traceback.print_exc(file=sys.stdout)
		print "<br><br>Fatal error.<br><br>"
		print "</div>\n</body>\n</html>"



def parsevote(v):
	v = v.lower()
	if "comment" in v:
		return None
	elif "note" in v:
		return None
	elif "merge" in v:
		return "Merge"
	elif "redirect" in v:
		return "Redirect"
	elif "speedy keep" in v:
		return "Speedy Keep"
	elif "speedy delete" in v:
		return "Speedy Delete"
	elif "keep" in v:
		return "Keep"
	elif "delete" in v:
		return "Delete"
	elif "transwiki" in v:
		return "Transwiki"
	elif ("userfy" in v) or ("userfied" in v) or ("incubat" in v) or ("draftify" in v):
		return "Userfy"
	else:
		return "UNDETERMINED"  
	
	
def parsetime(t):
	tm = re.search("\d{2}:\d{2}, (\d{1,2}) ([A-Za-z]*) (\d{4})", t)
	if tm == None:
		return ""
	else:
		return tm.group(2) + " " + tm.group(1) + ", " + tm.group(3)


def findresults(thepage):       #Parse through the text of an AfD to find how it was closed
	resultsearch = re.search("The result (?:of the debate )?was(?:.*?)(?:'{3}?)(.*?)(?:'{3}?)", thepage, flags=re.IGNORECASE)
	if resultsearch == None:
		if "The following discussion is an archived debate of the proposed deletion of the article below" in thepage or "This page is an archive of the proposed deletion of the article below." in thepage or "'''This page is no longer live.'''" in thepage:
			return "UNDETERMINED"
		else:
			return "Not closed yet"
	else:
		result = resultsearch.group(1).lower()
		if "no consensus" in result:
			return "No Consensus"
		elif "merge" in result:
			return "Merge"
		elif "redirect" in result:
			return "Redirect"
		elif "speedy keep" in result or "speedily kept" in result or "speedily keep" in result or "snow keep" in result or "snowball keep" in result or "speedy close" in result:
			return "Speedy Keep"
		elif "speedy delete" in result or "speedily deleted" in result or "snow delete" in result or "snowball delete" in result:
			return "Speedy Delete"
		elif "keep" in result:
			return "Keep"
		elif "delete" in result:
			return "Delete"
		elif "transwiki" in result:
			return "Transwiki"
		elif ("userfy" in result) or ("userfied" in result) or ("incubat" in result) or ("draftify" in result):
			return "Userfy"
		elif "withdraw" in result:
			return "Speedy Keep"
		else:
			return "UNDETERMINED"


def findDRV(thepage, pagename): #Try to find evidence of a DRV that was opened on this AfD
	try:
		drvs = ""
		drvcounter = 0
		for drv in re.finditer("(?:(?:\{\{delrev xfd)|(?:\{\{delrevafd)|(?:\{\{delrevxfd))(.*?)\}\}", thepage, flags=re.IGNORECASE):
			drvdate = re.search("\|date=(\d{4} \w*? \d{1,2})", drv.group(1), flags=re.IGNORECASE)
			if drvdate:
				drvcounter += 1
				name = re.search("\|page=(.*?)(?:\||$)", drv.group(1), flags=re.IGNORECASE)
				if name:
					nametext = urllib.quote(name.group(1))
				else:
					nametext = urllib.quote(pagename.replace("Articles_for_deletion/", "", 1))
				drvs += '<a href="http://en.wikipedia.org/wiki/Wikipedia:Deletion_review/Log/' + drvdate.group(1).strip().replace(" ", "_") + '#' + nametext + '"><sup><small>[' + str(drvcounter) + ']</small></sup></a>'
		return drvs
	except:
		return ""


def updatestats(v, r):  #Update the global statistics variable for votes
	global stats
	if v == "Merge":
		vv = "m"
	elif v == "Redirect":
		vv = "r"
	elif v == "Speedy Keep":
		vv = "sk"
	elif v == "Speedy Delete":
		vv = "sd"
	elif v == "Keep":
		vv = "k"
	elif v == "Delete":
		vv = "d"
	elif v == "Transwiki":
		vv = "t"
	elif v == "Userfy":
		vv = "u"
	else:
		return
	stats[v] += 1
	if r == "Merge":
		rr = "m"
	elif r == "Redirect":
		rr = "r"
	elif r == "Speedy Keep":
		rr = "sk"
	elif r == "Speedy Delete":
		rr = "sd"
	elif r == "Keep":
		rr = "k"
	elif r == "Delete":
		rr = "d"
	elif r == "Transwiki":
		rr = "t"
	elif r == "Userfy":
		rr = "u"
	elif r == "No Consensus":
		rr = "nc"
	else:
		return
	stats[vv+rr] += 1


def match(v, r, drv):   #Update the global matchstats variable
	global matchstats
	if r == "No Consensus":
		matchstats[2] += 1
		return '<td class="m">' + r + drv + '</td>'
	elif r == "Not closed yet":
		return '<td class="m">' + r + drv + '</td>'
	elif r == "UNDETERMINED":
		return '<td class="m">' + r + drv + '</td>'
	elif v == r:
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	elif v == "Speedy Keep" and r == "Keep":
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	elif r == "Speedy Keep" and v == "Keep":
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	elif v == "Speedy Delete" and r == "Delete":
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	elif r == "Speedy Delete" and v == "Delete":
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	elif r == "Redirect" and v == "Delete":
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	elif r == "Delete" and v == "Redirect":
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	elif r == "Merge" and v == "Redirect":
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	elif r == "Redirect" and v == "Merge":
		matchstats[0] += 1
		return '<td class="y">' + r + drv + '</td>'
	else:
		matchstats[1] += 1
		return '<td class="n">' + r + drv + '</td>'


def matrixmatch(v, r):  #Returns html to color the cell of the matrix table correctly, depending on whether there is a match/non-match (red/green), or if the cell is zero/non-zero (bright/dull).
	global stats
	if stats[v+r]:
		if r=="nc":
			return '<td class="mm">'
		elif v == r:
			return '<td class="yy">'
		elif v=="sk" and r=="k":
			return '<td class="yy">'
		elif v=="k" and r=="sk":
			return '<td class="yy">'
		elif v=="d" and r=="sd":
			return '<td class="yy">'
		elif v=="sd" and r=="d":
			return '<td class="yy">'
		elif v=="d" and r=="r":
			return '<td class="yy">'
		elif v=="r" and r=="d":
			return '<td class="yy">'
		elif v=="m" and r=="r":
			return '<td class="yy">'
		elif v=="r" and r=="m":
			return '<td class="yy">'
		else:
			return '<td class="nn">'
	else:
		if r=="nc":
			return '<td class="mmm">'
		elif v == r:
			return '<td class="yyy">'
		elif v=="sk" and r=="k":
			return '<td class="yyy">'
		elif v=="k" and r=="sk":
			return '<td class="yyy">'
		elif v=="d" and r=="sd":
			return '<td class="yyy">'
		elif v=="sd" and r=="d":
			return '<td class="yyy">'
		elif v=="d" and r=="r":
			return '<td class="yyy">'
		elif v=="r" and r=="d":
			return '<td class="yyy">'
		elif v=="m" and r=="r":
			return '<td class="yyy">'
		elif v=="r" and r=="m":
			return '<td class="yyy">'
		else:
			return '<td class="nnn">'
			

def APIpagedata(rawpagelist):   #Grabs page text for all of the AfD's using the API
	try:
		p = ''
		for page in rawpagelist:
			p += urllib.quote("Wikipedia:" + page[0].replace("_", " ") + "|")
		u = urllib.urlopen("http://en.wikipedia.org/w/api.php?action=query&prop=revisions|info&rvprop=content&format=xml&titles=" + p[:-3])
		xml = u.read()
		u.close()
		pagelist = re.findall(r'<page.*?>.*?</page>', xml, re.DOTALL)
		pagedict = {}
		for i in pagelist:
			try:
				pagename = re.search(r'<page.*?title=\"(.*?)\"', i).group(1)
				text = re.search(r'<rev.*?xml:space="preserve">(.*?)</rev>', i, re.DOTALL).group(1)
				if re.search('<page.*?redirect=\"\".*?>', i):	 #AfD page is a redirect
					continue
				pagedict[unescape(pagename)] = text
			except:
				continue
		return pagedict
	except:
		errorout("Unable to fetch page data.  Please try again.")


def APIfirsteditor(p):	#Finds the name of the user who created a particular page, using the API.  Deprecated, using db query instead, see DBfirsteditor()
	try:
		u = urllib.urlopen("http://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles=Wikipedia:" + urllib.quote(p) + "&rvlimit=1&rvprop=timestamp|user&rvdir=newer&format=xml")
		xml = u.read()
		u.close()
		s = re.search("<rev user=\"(?P<user>.*?)\" timestamp=\"(?P<timestamp>.*?)\" />", xml)
		user = s.group("user")
		timestamp = re.search("(\d{4})-(\d{2})-(\d{2})", s.group("timestamp"))
		monthmap = {"01":"January", "02":"February", "03":"March", "04":"April", "05":"May", "06":"June", "07":"July", "08":"August", "09":"September", "10":"October", "11":"November", "12":"December"}
		timestamptext = monthmap[timestamp.group(2)] + " " + timestamp.group(3).lstrip("0") + ", " + timestamp.group(1)
		return (user, timestamptext)
	except:
		return None

def DBfirsteditor(p, cursor):   #Finds the name of the user who created a particular page, using a database query.  Replaces APIfirsteditor()
        try:
                cursor.execute("SELECT actor_name, rev_timestamp FROM revision JOIN page ON rev_page=page_id JOIN actor ON actor_id=rev_actor WHERE rev_parent_id=0 AND page_title=%s AND page_namespace=4;", (p.replace(" ", "_"),))
                results = cursor.fetchall()[0]
                return (results[0], datetime.datetime.strptime(results[1], "%Y%m%d%H%M%S").strftime("%B %d, %Y"))
        except:
                return None


def unescape(s):
	p = htmllib.HTMLParser(None)
	p.save_bgn()
	p.feed(s)
	return p.save_end()


def datefmt(datestr):
    try:
        tg = re.search("([A-Za-z]*) (\d{1,2}), (\d{4})", datestr)
        if tg == None:
            return ""
        monthmap = {"01":"January", "02":"February", "03":"March", "04":"April", "05":"May", "06":"June", "07":"July", "08":"August", "09":"September", "10":"October", "11":"November", "12":"December"}
        month = [k for k,v in monthmap.items() if v==tg.group(1)][0]
        day = tg.group(2)
        year = tg.group(3)
        if len(day) == 1:
            day = "0" + day
        return year + month + day
    except:
        return ""


def link(p):
    text = cgi.escape(p.replace("_", " ")[22:])
    if len(text) > 64:
        text = text[:61] + "..."
    return '<a href="http://en.wikipedia.org/wiki/Wikipedia:' + urllib.quote(p) + '">' + text + '</a>'


def errorout(errorstr):         #General error handler, prints error message and aborts execution.
	print "<p>ERROR: " + errorstr + "</p><p>Please <a href='http://tools.wmflabs.org/afdstats/'>try again</a>.</p>"
	print FOOTER
	print "</div></body>\n</html>"
	sys.exit(0)
	
main()
