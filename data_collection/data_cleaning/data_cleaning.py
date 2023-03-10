import json
import pandas as pd
import numpy as np
import mwparserfromhell
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from datetime import datetime
import os
import sys
sys.path.append('/home/dylan/python-mwchatter/')
import wikichatter as wc


wikipedia_project_string = 'wikipedia'
wikidata_project_string = 'wikidata'
meta_project_string = 'meta.wikimedia'


def get_RFC_Comment_Table(wikipedia, wikidata, meta):
    projects_list = [wikipedia,wikidata,meta]
    for project in projects_list:
        project = removeDuplicatePages(project)
    projects_list = addProjectName(projects_list)
    concat_list = projects_list[0] + projects_list[1] + projects_list[2]
    return concat_list, createRfcTable(concat_list)

def find_matching_closed_rfc_tags(text):
    """
    Find the positions of the {{closed rfc top}} and {{closed rfc bottom}} tags in a text and return the position of the
    first matching pair of tags.
    :param text: The text to search for tags.
    :return: A tuple of integers representing the positions of the top and bottom tags for the first matching pair, or None
    if no matching pair is found.
    """
    top_tag = '{{closed rfc top'
    bottom_tag = '{{closed rfc bottom}}'
    top_tag_pos = None
    bottom_tag_pos = None
    open_tags = []
    if text is None:
        return text
    for x, comment in enumerate(text):
        if comment == None:
            continue
        lower = comment['text'].lower()
        for i, char in enumerate(lower):
                    if char == '{' and lower[i:i+len(top_tag)] == top_tag:
                        open_tags.append(x)
                    elif char == '{' and lower[i:i+len(bottom_tag)] == bottom_tag:
                        if open_tags:
                            top_tag_pos = open_tags.pop()
                            bottom_tag_pos = x
                            if not open_tags:
                                return (top_tag_pos, bottom_tag_pos)                     
    if len(open_tags) == 1:
        return open_tags

def addProjectName(projects_list):
    for page in projects_list[0]:
        for obj in page['page_text']:
            obj['project'] = wikipedia_project_string
    for page in projects_list[1]:
        for obj in page['page_text']:
            obj['project'] = wikidata_project_string
    for page in projects_list[2]:
        for obj in page['page_text']:
            obj['project'] = meta_project_string
    return projects_list

def removeDuplicatePages(list_of_dicts):
    #removing duplicates
    # create a set to store unique tuples of objects
    unique_objs = set()
    final_list = []
    # loop through the list of json objects
    for obj in list_of_dicts:
        # convert json object to tuple
        page_id = (obj['page_id'],str(obj['page_text']))
        # check if the tuple is already in the set
        if page_id not in unique_objs:
            unique_objs.add(page_id)
            final_list.append(obj)
    return final_list

def parseWikipediaText(project_list):
    """
    Checking if comments on page are in the closed rfc
    """
    list_of_dicts = project_list[0]
    loc = None
    for page in list_of_dicts:
        loc = find_matching_closed_rfc_tags(page['page_text'])
        if loc == None:
            list_of_dicts.remove(page)
            continue
        elif len(loc) == 1:
            page['page_text'] = page['page_text'][loc[0]:]
        elif len(loc) == 2:
            page['page_text'] = page['page_text'][loc[0]:loc[1]]

        newPageList = []
        first_entry_dic = parseClosedRFC(page['page_text'][0]['text'])
        if first_entry_dic:
            first_entry_dic['section'] = page['page_text'][0]['section']
            first_entry_dic['parent_id'] = 0
            first_entry_dic['id'] = page['page_text'][0]['id'] - 1
            newPageList.append(first_entry_dic)
            page['page_text'][0]['text'] = page['page_text'][0]['text'].replace(first_entry_dic['text'],'')
            page['page_text'] = newPageList + page['page_text']
    return project_list

def parseClosedRFC(text):
    parsed_text = wc.parse(text)
    parsed_text_dic = {}
    if not 'author' in parsed_text['sections'][0]['comments'][0]:
        return None
    parsed_text_dic['text'] = parsed_text['sections'][0]['comments'][0]['text_blocks'][0]
    parsed_text_dic['user'] = parsed_text['sections'][0]['comments'][0]['author']

    # parse the input string into a datetime object
    input_datetime = datetime.strptime(parsed_text['sections'][0]['comments'][0]['time_stamp'], "%H:%M, %d %B %Y (%Z)")

    # format the datetime object in the desired output format
    output_str = input_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

    parsed_text_dic['date'] = output_str

    return parsed_text_dic

def createRfcTable(list_of_dicts):
    rf_list = []
    loc = None
    count = 0
    comment_counter = 0
    for page in list_of_dicts:
        mediawiki_project = page['page_text'][0]['project']
        if mediawiki_project == 'wikipedia':
            rf_list.append({"page_id": page['page_id'], "rfc_id" : count, "page_title" : page['page_title'], "discussion_input_comment" : comment_counter, 'project' : mediawiki_project})
        else:
            rf_list.append({"page_id": page['page_id'],"rfc_id" : count, "page_title" : page['page_title'], "discussion_input_comment" : comment_counter, 'project' : mediawiki_project})

        dif =  page['page_text'][0]['id'] - comment_counter
        for i, comment in enumerate(page['page_text']):
            comment['rfc_id'] = int(count)
            comment['id'] = comment_counter

            if comment['parent_id'] != 0:
                comment['parent_id'] = comment['parent_id'] - dif
            comment_counter = comment_counter + 1
        count = count + 1
    return rf_list

def getTemplateVisualText(template,project):
    """
    Gets the HTML for a template that is displayed and returns as simple text
    """
    S = requests.Session()

    URL = f"https://{project}.org/w/api.php"

    PARAMS = {
        "action": "expandtemplates",
        "text": f'{template}',
        "prop": "wikitext",
        "format": "json"
    }

    R = S.get(url=URL, params=PARAMS)
    if R: 
        DATA = R.json()
        soup = BeautifulSoup(DATA['expandtemplates']['wikitext'], 'html.parser')
        return soup.get_text()
    else:
        return str(template)


def templatesToReadableText(dataframe):
    if os.path.exists('wikipedia_template_dic.json'):
        with open('wikipedia_template_dic.json') as f:
            wikipedia_template_dic = json.load(f)
    if os.path.exists('wikidata_template_dic.json'):
        with open('wikidata_template_dic.json') as f:
            wikidata_template_dic = json.load(f)
    if os.path.exists(f'{meta_project_string}_template_dic.json'):
        with open(f'{meta_project_string}_template_dic.json') as f:
            meta_wikimedia_template_dic = json.load(f)
    else:
        wikipedia_template_dic = {}
        wikidata_template_dic = {}
        meta_wikimedia_template_dic = {}

    for i in tqdm(range(0,len(dataframe))):
        text = dataframe.at[i,'text']
        templates = mwparserfromhell.parse(text).filter_templates()
        for template in templates:
            project = dataframe.at[i,'project']
            if template.startswith('{{P|'):
                project = 'wikidata'
            string = template.__str__()
            
            if project == wikipedia_project_string:
                if string not in wikipedia_template_dic:
                    template_html = getTemplateVisualText(string, project)
                    wikipedia_template_dic[string] = template_html
                    text = text.replace(string, template_html)
                else:
                    text = text.replace(string, wikipedia_template_dic[string])
                dataframe.at[i,'text'] = mwparserfromhell.parse(text).strip_code(collapse = True,keep_template_params=False)
        
            if project == wikidata_project_string:
                if string not in wikidata_template_dic:
                    template_html = getTemplateVisualText(string, project)
                    wikidata_template_dic[string] = template_html
                    text = text.replace(string, template_html)
                else:
                    text = text.replace(string, wikidata_template_dic[string])
                dataframe.at[i,'text'] = mwparserfromhell.parse(text).strip_code(collapse = True,keep_template_params=False)
        
        
            if project == meta_project_string:
                if string not in meta_wikimedia_template_dic:
                    template_html = getTemplateVisualText(string, project)
                    meta_wikimedia_template_dic[string] = template_html
                    text = text.replace(string, template_html)
                else:
                    text = text.replace(string, meta_wikimedia_template_dic[string])
                dataframe.at[i,'text'] = mwparserfromhell.parse(text).strip_code(collapse = True,keep_template_params=False)
            
    with open(f'{wikipedia_project_string}_template_dic.json', 'w') as file:
        json.dump(wikipedia_template_dic, file)

    with open(f'{wikidata_project_string}_template_dic.json', 'w') as file:
        json.dump(wikidata_template_dic, file)

    with open(f'{meta_project_string}_template_dic.json', 'w') as file:
        json.dump(meta_wikimedia_template_dic, file)