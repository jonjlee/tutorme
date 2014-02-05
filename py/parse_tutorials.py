#!/usr/bin/env python
import sys
import codecs
import pprint 
import re
import json
import urllib
from gdatasheet import GDataSheet

import bs4
from bs4 import BeautifulSoup as BS

UTF8Writer = codecs.getwriter('utf8')
sys.stdout = UTF8Writer(sys.stdout)
pp = pprint.PrettyPrinter(indent=4)

EDITS_GFORM_KEY = '0ArXWeP4vbbvJdExxRmtfOU5janpMMVU4N2lXWlQxcVE'

RE_QUESTION_SECTION = re.compile(u'Part\s+[0-9]') 
RE_CHOICES_SECTION = re.compile(u'([A-Z]|[0-9]+)\s*\.\xa0+')
RE_ANSWER_SECTION = re.compile(u'Answers\s*\.?|The correct answer is|Answer\s+[A-Z]\s+is|Answers?\s+[A-Z]\s+and\s+[A-Z]\s|[A-Z]\.[\xa0\s]+[0-9]+\.[\xa0\s]+|[0-9]+\.[\xa0\s]+[A-Z]|[0-9]+\.[\xa0\s]+[A-Z]\.')
RE_MATCHING_ANSWER = re.compile(u'[A-Z]\.[\xa0\s]+[0-9]+\.[\xa0\s]+|[0-9]+\.[\xa0\s]+[A-Z]\.?')
RE_IMAGE_SRC = re.compile('^.*\/([^\/]+)$')
RE_PAGEBREAK = re.compile('page-break-before:always')

def isempty(obj):
	return (istag(obj) and len(obj.contents) == 0) or (obj == '')

def istag(obj):
	return isinstance(obj, bs4.element.Tag)

def getattr(obj, attr):
	return attr in obj.attrs and obj[attr] or None

def remove_mso_classes(tag):
	classes = tag.get('class')
	if classes:
		for i in range(len(classes)-1, -1, -1):
			if 'Mso' in classes[i]: del classes[i]

def cleantag(tag):
	''' Removes all "style" attributes and comments from tag. Modifies tag directly. '''
	if tag.get('style'): del tag['style']
	remove_mso_classes(tag)
	if tag.get('class') and 'Mso' in tag['class']: del tag['class']
	for node in tag.find_all():
		if node.get('style'): del node['style']
		remove_mso_classes(node)
	for node in tag.find_all('img'):
		if node.get('src'): node['src'] = RE_IMAGE_SRC.sub('static/img/tutorials/\\1', node['src'])
	for node in tag.findAll(text=lambda text: isinstance(text, bs4.Comment)):
		node.extract()
	for node in tag.findAll(lambda tag: ':' in tag.name):
		node.extract()
	return tag

def parse(soup):
	'''Split into sections, questions, answers, and tutorial. Returns:
		[{ 
			'section': 'Rheumatology',
			'questions': [
				{
					'question': '<p>What is the most likely diagnosis?</p><p>A. Endocarditis</p><p>B. Sepsis</p>'
					'answer': '<p><b>Answer A</b>. is correct.</p><h4>Tutorial</h4><p>The presenting symptoms are classic for endocarditis.</p>'
				}, ...
			]
		}, ...]
	'''
	sections = []

	# body is divided into several divs. Each div contains many p elements.
	# If there is no containing div, then just use body.
	divs = soup.body.find_all('div', recursive=False)
	if not divs or not divs[0].text: divs = soup.body

	data, tutorial, section, obj = '', '', None, None
	empty_lines, new_page = 0, False
	state = 'start'

	for div in divs:
		tags = div.find_all(recursive=False)
		numtags = len(tags)
		prev, tag, next = None, None, None

		for i in xrange(0, numtags-1):
			# Set prev, tag, and next to point to corresponding tags
			tag = tags[i]
			if i == numtags-1: next = None
			else: next = tags[i+1]

			# Ignore any content in root div that isn't a tag
			if not istag(tag): continue
			tagstate = tag.get('section')

			# Ignore all blank paragraphs
			br = (tag.name == 'br' and tag) or tag.find('br')
			if (br and RE_PAGEBREAK.search(br.get('style') or '')): # or (not new_page and empty_lines > 3):
				new_page = True
				continue
			else:
				text = tag.text.replace(u'\n', ' ').strip()
				if len(text) == 0 and not tag.select('img'): 
					empty_lines += 1
					continue
				empty_lines = 0

			is_section = (tag.name == 'p' and tag.span and ('style' in tag.span.attrs) and ('font-size:72.0pt' in tag.span['style']))
			is_choices_list = (tag.name == 'ol' and tag.get('type') == 'A') or tag.select('table td[width=23]')
			is_answers_list = (tag.name == 'ol' and tag.get('type') == '1')

			# Remove class and style attributes and extraneous namespaced tags
			html = cleantag(tag).prettify(formatter='html')

			if tag.name == 'div' and not tag.table:
				sys.stderr.write('Unexpected <div> found at tag %d: "%s...\n"' % (i, text[:100]))

			# Detect any new state transitions
			if state != 'section' and (is_section or tag.select('span.Section')):
				# Store the last question before starting a new section
				if 'answers' in state:
					obj['answer'] = data + '\n' + tutorial
					section['questions'].append(obj)

				data = ''
				if section: sections.append(section)
				section = {'section': '', 'questions': []}
				state = 'section'

			elif state == 'section':
				if tagstate == 'question' or not (is_section or tag.select('span.Section')):
					section['section'] = data
					obj = {'question': '', 'answer': ''}
					data = ''
					state = 'question'

			elif state == 'question':
				if new_page:
					obj['question'] = data
					tutorial, data = '', ''

					if is_answers_list or RE_ANSWER_SECTION.match(text) or RE_MATCHING_ANSWER.match(text):
						state = 'answers'
					else:
						state = 'tutorial'

			elif state == 'tutorial':
				if new_page:
					if data: tutorial = '<div class="row">&nbsp;</div><div class="row text-center"><h4>Tutorial</h4></div>\n' + data
					data, state = '', 'answers'

			elif state == 'answers':
				if new_page:
					obj['answer'] = data + '\n' + tutorial
					section['questions'].append(obj)
					obj, data, state = {'question': '', 'answer': ''}, '', 'question'

			# Safe-guard to recover in the event that a page break caused a frame-shift. Detects start of answer section.
			if state != 'answers' and new_page and RE_ANSWER_SECTION.match(text):
				sys.stderr.write('Frame-shift detected at tag %d: "%s ... %s". Recovering from %s to answer section.\n' % (i, prev.text[:20], text[-20:], state))
				state = 'answers'
				data, state = '', 'answers'

			# Process tag given current state
			if state == 'section':
				# Combine multi-line section headings (e.g. Rheumatology, Allergy, & Immunology)
				if not len(data) or data == 'Clinical Transitions 2014':
					data = text
				else:
					data = u' '.join([data, text])
			else:
				# Remove all &nbsp; from choices
				if 'question' in state:
					html = html.replace(u'\xa0', '')

				# Append new paragraph/element to current section
				if not len(data):
					data = html
				else:
					data = u'\n'.join([data, html])

			# Processed non-blank element, so next element no longer starts a new page
			new_page = False
			prev = tag


	# Save the last question and last section
	if 'answers' in state:
		obj['answer'] = data + '\n' + tutorial
		section['questions'].append(obj)
	if section:
		sections.append(section)

	return sections

def apply_edits(obj, gform_key):
	'''Read editorial changes from Google Sheets and override contents in obj with edits.
	   The sheet should have 3 columns: Timestamp, ID (e.g. g,0,1), Content (e.g. <p>Editorial content</p>)
	'''
	edits = GDataSheet().open(gform_key)
	for row in edits.rows(ncols=3):
		if len(row) < 3 or row[1] is None: continue

		# Parse ID from column 2
		edit_type, section_num, question_num = row[1].split(',')
		section_num = int(section_num)
		question_num = int(question_num)

		if section_num < len(obj) and question_num < len(obj[section_num]['questions']):
			# Un-html encode content in column 3 if necessary (i.e. if '<p' is found)
			content = row[2]
			if '%3Cp' in content: content = urllib.unquote(content)

			# Override current content with editorial content
			if edit_type == 'q':
				obj[section_num]['questions'][question_num]['question'] = content
			elif edit_type == 'a':
				obj[section_num]['questions'][question_num]['answer'] = content

	return obj

def to_html(obj):
	html = [u'<html><head></head><body>']
	for section in obj:
		html.append(u'<h2>%s</h2>\n' % section['section'])
		for question in section['questions']:
			html.append(u'<h4>Question</h4>')
			html.append(question['question'])
			html.append(u'\n')
			html.append(u'<h4>Answer</h4>')
			html.append(question['answer'])

	html.append(u'</body></html>')
	return u'\n'.join(html)

def main(source_file='Tutorials.htm'):
	# Parse HTML
	sys.stderr.write('Reading file...\n')
	f = open(source_file)
	soup = BS(f)
	f.close()

	sys.stderr.write('Parsing HTML...\n')
	obj = parse(soup)

	sys.stderr.write('Reading edits from Google Sheet...\n')
	obj = apply_edits(obj, EDITS_GFORM_KEY)
	
	print u'data = %s' % json.dumps(obj)
	
	# html = to_html(obj)
	# pp.pprint(obj)

if __name__ == '__main__':
	main(len(sys.argv) > 1 and sys.argv[1] or 'Tutorials.htm')
