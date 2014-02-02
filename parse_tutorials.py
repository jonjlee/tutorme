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

RE_QUESTION_SECTION = re.compile(u'Part\s+[0-9]') 
RE_CHOICES_SECTION = re.compile(u'([A-Z]|[0-9]+)\s*\.\xa0+')
RE_ANSWER_SECTION = re.compile(u'Answers\s*\.?|The correct answer is|Answer\s+[A-Z]\s+is|Answers?\s+[A-Z]\s+and\s+[A-Z]\s|[A-Z]\.[\xa0\s]+[0-9]+\.[\xa0\s]+|[0-9]+\.[\xa0\s]+[A-Z]|[0-9]+\.[\xa0\s]+[A-Z]\.')

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
	for node in tag.findAll(text=lambda text: isinstance(text, bs4.Comment)):
		node.extract()
	for node in tag.findAll(lambda tag: ':' in tag.name):
		node.extract()
	return tag

def parse(soup):
	'''Split into sections, questions, answers, and tutorial'''
	sections = []

	divs = soup.body.find_all('div', recursive=False)
	data = ''
	section = None
	obj = None
	state = 'start'
	for div in divs:
		for tag in div:
			# Ignore any content in root div that isn't a tag
			if not istag(tag): continue
			tagstate = tag.get('section')

			# Ignore all blank paragraphs
			text = tag.text.replace(u'\n', ' ').strip()
			if len(text) == 0 and not tag.select('img'): continue
			html = cleantag(tag).prettify(formatter='html')

			is_choices_list = (tag.name == 'ol' and tag.get('type') == 'A') or tag.select('table td[width=23]')
			is_answers_list = (tag.name == 'ol' and tag.get('type') == '1')

			# Detect any new state transitions
			if state != 'section' and tag.select('span.Section'):
				# Store the last question before starting a new section
				if state == 'answers':
					obj['answers'] = data
					section['questions'].append(obj)

				data = ''
				if section: sections.append(section)
				section = {'section': '', 'questions': []}
				state = 'section'

			elif state == 'section':
				if tagstate == 'question' or not tag.select('span.Section'):
					section['section'] = data
					obj = {'question': '', 'choices': [], 'tutorial': '', 'answers': ''}
					data = ''
					state = 'question'

			elif state == 'question' and tagstate != 'question':
				if tagstate == 'choices' or is_choices_list or RE_CHOICES_SECTION.match(text):
					obj['question'] = data
					data = []
					state = 'choices'

			elif state == 'choices' and tagstate != 'choices':
				if tagstate == 'answers' or is_answers_list or RE_ANSWER_SECTION.match(text):
					obj['choices'] = data
					data = []
					state = 'answers'
				elif tagstate == 'tutorial' or not (is_choices_list or RE_CHOICES_SECTION.match(text)):
					obj['choices'] = data
					data = ''
					state = 'tutorial'

			elif state == 'tutorial' and tagstate != 'tutorial':
				if tagstate == 'answers' or is_answers_list or RE_ANSWER_SECTION.match(text):
					obj['tutorial'] = data
					data = []
					state = 'answers'

			elif state == 'answers' and tagstate != 'answers':
				if tagstate == 'question' or not (is_answers_list or RE_ANSWER_SECTION.match(text) or re.match(u'\*?Note\s*:', text)):
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
				data.append(html.replace(u'\xa0', ''))

			if state == 'answers':
				data.append(html)

			if state == 'question' or state == 'tutorial':
				if not len(data): data = html
				else: data = u'\n'.join([data, html])

	# Save the last question and last section
	if state == 'answers':
		obj['answers'] = data
		section['questions'].append(obj)
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
