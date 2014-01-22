#!/usr/bin/env python
import sys
import codecs
import pprint 
import re
import json

import bs4
from bs4 import BeautifulSoup as BS

UTF8Writer = codecs.getwriter('utf8')
sys.stdout = UTF8Writer(sys.stdout)
pp = pprint.PrettyPrinter(indent=4)

def isempty(obj):
	return (istag(obj) and len(obj.contents) == 0) or (obj == '')

def istag(obj):
	return isinstance(obj, bs4.element.Tag)

def getattr(obj, attr):
	return attr in obj.attrs and obj[attr] or None

def parse(soup):
	'''Split into sections, questions, answers, and tutorial'''
	sections = []

	tags = soup.body.div
	data = ''
	section = None
	obj = None
	state = 'start'
	for tag in tags:
		# Ignore any content in root div that isn't a tag
		if not istag(tag): continue

		# Ignore all blank paragraphs
		text = tag.text.replace(u'\n', ' ').strip()
		if len(text) == 0 and not tag.select('img'): continue
		html = tag.prettify(formatter='html')


		# Detect any new state transitions
		if state != 'section' and tag.select('span.Section'):
			data = ''
			if section: sections.append(section)
			section = {'section': '', 'questions': []}
			state = 'section'

		elif state == 'section' and not tag.select('span.Section'):
			section['section'] = data
			obj = {'question': '', 'choices': [], 'tutorial': '', 'answers': ''}
			data = ''
			state = 'question'

		elif state == 'question' and re.match(u'[A-Z]\.\xa0\xa0', tag.text):
			obj['question'] = data
			data = []
			state = 'choices'

		elif state == 'choices' and not re.match(u'[A-Z]\.\xa0\xa0', tag.text):
			obj['choices'] = data
			data = ''
			state = 'tutorial'

		elif state == 'tutorial' and re.match(u'Answer\s+[A-Z]\s+is', tag.text):
			obj['tutorial'] = data
			data = []
			state = 'answers'

		elif state == 'answers' and not re.match(u'Answer\s+[A-Z]\s+is', tag.text):
			obj['answers'] = data
			section['questions'].append(obj)
			obj = {'question': '', 'choices': [], 'tutorial': '', 'answers': ''}
			data = ''
			state = 'question'

		# Process tag given current state
		if state == 'section':
			# Combine multi-line section headings (e.g. Rheumatology, Allergy, & Immunology)
			if not len(data): data = text
			else: data = u' '.join([data, text])

		if state == 'choices':
			data.append(text.replace(u'\xa0', ''))

		if state == 'answers':
			data.append(html)

		if state == 'question' or state == 'tutorial':
			if not len(data): data = html
			else: data = u'\n'.join([data, html])

	if section: sections.append(section)
	return sections

def to_html(obj):
	html = [u'<html><head></head><body>']
	for section in obj:
		html.append(u'<h2>%s</h2>\n' % section['section'])
		for question in section['questions']:
			html.append(u'<h4>Question</h4>')
			html.append(question['question'])
			html.append(u'\n')
			html.append(u'<h4>Choices</h4>')
			for choice in question['choices']:
				html.append(u'<p>%s</p>' % choice)
			html.append(u'\n')
			html.append(u'<h4>Tutorial</h4>')
			html.append(question['tutorial'])
			html.append(u'\n')
			html.append(u'<h4>Answers</h4>')
			for answer in question['answers']:
				html.append(answer)

	html.append(u'</body></html>')
	return u'\n'.join(html)

def main(source_file='Tutorials.htm'):
	# Parse HTML
	f = open(source_file)
	soup = BS(f)
	f.close()

	obj = parse(soup)
	html = to_html(obj)

	print u'data = %s' % json.dumps(obj)
	# pp.pprint(obj)

if __name__ == '__main__':
	main(len(sys.argv) > 1 and sys.argv[1] or 'Tutorials.htm')
