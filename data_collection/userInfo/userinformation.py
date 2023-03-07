''' userinformation.py '''
#Functions for getting data from MongoDB across different projects
import pymysql
import pandas as pd
import json
import re
from datetime import date, timedelta,datetime
import multiprocessing
import tqdm
import time

def make_connection(wiki, replica_type="analytics"):
    """Connects to a host and database of the same name.
    
    `replica_type` can be either "analytics" (default), or "web"."""
    assert replica_type == "web" or replica_type == "analytics"
    return pymysql.connect(
        host=f"{wiki}.{replica_type}.db.svc.wikimedia.cloud",
        read_default_file="~/.my.cnf",
        database=f"{wiki}_p",
        charset='utf8'
    )

def query(conn, query):
    """Execute a SQL query against the connection, and return **all** the results."""
    with conn.cursor() as cur:
        cur.execute(query)
        data = cur.fetchall()
        return data
    
def getActorID(username, wiki):
    commons_conn = make_connection(f'{wiki}')
    sql_string = f"SELECT * FROM actor WHERE actor_name='{username}'"
    results = query(
        commons_conn,
        sql_string
    )
    commons_conn.close()
    if results:
        return results[0][0]
    else:
        return None
    
def getUserID(username, wiki):
    commons_conn = make_connection(f'{wiki}')
    sql_string = f"SELECT user_id FROM user WHERE user_name='{username}'"
    results = query(
        commons_conn,
        sql_string
    )
    commons_conn.close()
    if results:
        return results[0][0]
    else:
        return None

def getFirstActorCommentDate(actorID,wiki):
    commons_conn = make_connection(f"{wiki}")
    results = query(
        commons_conn,
        f"SELECT MIN(rev_timestamp) FROM revision INNER JOIN comment ON revision.rev_comment_id=comment.comment_id WHERE rev_actor='{actorID}';"
    )
    commons_conn.close()
    if results:
        return results[0][0]
    else:
        return None

def getUserRegistrationDate(user_name,wiki):
    
    commons_conn = make_connection(f"{wiki}")
    results = query(
        commons_conn,
        f"SELECT user_registration FROM user WHERE user_name='{user_name}';"
    )
    commons_conn.close()
    if results:
        return results[0][0]
    else:
        return None
    
def getUserInformation(user_name, wiki_list):
    #getting base user information from mediawiki 
    commons_conn = make_connection("mediawikiwiki")
    results = query(
        commons_conn,
        f"SELECT user_id,user_name,user_real_name, user_registration, user_editcount FROM user WHERE user_name='{user_name}';"
    )
    commons_conn.close()
    
    if results:
        userDic = {'user_id' : results[0][0], 'user_name' : results[0][1].decode("utf-8"),'user_real_name' : results[0][2].decode("utf-8")}
    else:
        userDic = {'user_id' : None, 'user_name' : user_name, 'user_real_name' : None}
    
    
    #looping through all wiki projects, getting user rights, edit count, registration and first comment dates
    wiki_editcount_dic = {}
    wiki_permissions_dic = {}
    first_comment_date_list = []
    registration_date = []
    
    for wiki in wiki_list:
        wiki_editcount_dic[wiki] = getUserEditCount(user_name, wiki)
        id = getUserID(user_name,wiki)
        wiki_permissions_dic[wiki] = getUserGroups(id, wiki)
        first_comment_date = getFirstActorCommentDate(getActorID(user_name,wiki),wiki)
        regis_date = getUserRegistrationDate(user_name,wiki)
        if first_comment_date:
            first_comment_date_list.append(first_comment_date)
        if regis_date:
            registration_date.append(regis_date)
    #user does not exist in any project database anymore
    if not registration_date:
        userDic['isDeleted'] = True
        userDic['user_registration'] = None
        userDic['seconds_between_regdate_and_first_edit_date'] = None
        userDic['editcount'] = None
        userDic['permissions'] = None
    else:
        registration = datetime.strptime(min(registration_date).decode("utf-8"), "%Y%m%d%H%M%S")
        
        if first_comment_date_list:
            first_comment = datetime.strptime(min(first_comment_date_list).decode("utf-8"), "%Y%m%d%H%M%S")
            #calc time between registration and first comment
            delta = first_comment - registration
            userDic['seconds_between_regdate_and_first_edit_date'] = delta.total_seconds()
        #user never made a revision
        else:
            first_comment = None
            userDic['seconds_between_regdate_and_first_edit_date'] = None
        
        #setting values for user inf
        userDic['isDeleted'] = False
        userDic['user_registration'] = registration.isoformat()
        userDic['editcount'] = wiki_editcount_dic
        userDic['permissions'] = wiki_permissions_dic
    return userDic

def getUserEditCount(user_name, wiki):
    actor_id = getActorID(user_name, wiki)
    commons_conn = make_connection(f"{wiki}")
    results = query(
        commons_conn,
        f"SELECT COUNT(*) FROM revision WHERE rev_actor = '{actor_id}';"
    )
    commons_conn.close()
    if results:
        return results[0][0]
    else:
        return None
    
def getUserInfoAcrossAllReplicaDatabases(user):
    #not going over all wikis too much data
    '''
    commons_conn = make_connection("meta")
    results = query(
        commons_conn,
        'SELECT dbname, url, is_closed from wiki;'
    )
    commons_conn.close()
    replica_databases = pd.DataFrame(results)
    replica_databases.head()
    replica_databases_list = replica_databases[0].tolist()
    '''
    #prepare username for sql
    escaped_string = user.replace("'", "''")
    escaped_string2 = escaped_string.replace("\\", "\\\\")
    wiki_list = ['mediawikiwiki','metawiki','wikidatawiki', 'enwiki','eswiki','frwiki','dewiki','zhwiki','jawiki','plwiki','ruwiki','itwiki','nlwiki', 'ptwiki']
    return getUserInformation(escaped_string2,wiki_list)

def getUserGroups(user_id, wiki):
    commons_conn = make_connection(f"{wiki}")
    results = query(
        commons_conn,
        f"SELECT ug_group FROM user_groups WHERE ug_user='{user_id}';"
    )
    commons_conn.close()
    #returns bot, burocrat, sysop 
    if results:
        return results[0][0].decode("utf-8")
    else:
        return "user"
    

def getUserInfoToJSON(userArray, output):
    """
    Takes list of users outputs list of JSON objects containing wiki projects, user rights, edit count, registration and first comment dates
    """ 
    with multiprocessing.Pool(processes=7) as pool:
        results = list(tqdm.tqdm(pool.imap(worker, userArray)))
        with open(output, 'w') as file:
            json.dump(list(results), file)
    
    
def worker(user):
    try:
        userDic = getUserInfoAcrossAllReplicaDatabases(user)
        return userDic
    except:
        print(f"failed to get userDic, with {user}")

