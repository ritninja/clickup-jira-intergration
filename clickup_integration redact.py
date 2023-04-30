import requests
import os
import time
from atlassian import Jira


# Return comment text if the ClickUp task comment has attachments
def task_has_attachment(task_data):
    for comment in task_data['comments']:
        if "em7pp" in comment['comment_text']:
            return comment['comment_text']
    return ""


# Return a list of attachments from data and filtered out based on blacklist
def get_attachments(data, blacklist):
    attachment_list = []
    for comment in data['comments']:
        if "em7pp" in comment['comment_text']:
            for com in comment['comment']:
                if 'attachment' in com.keys():
                    if com['attachment'] is not None and not any([x in com['attachment']['url'] for x in blacklist]):
                        attachment_list.append(com['attachment']['url'])
    return attachment_list


# Variables
headers = {"Authorization": "CLICKUP_API_KEY"}
team_id = "CLICKUP_TEAM_ID"
project_id = "CLICKUP_PROJECT_ID"
attachment_blacklist = ['.png', '.jpg', '.html', '.ics']
jira = Jira(
    url='JIRA_CLOUD_URL',
    username="JIRA_CLOUD_USERNAME",
    password='JIRA_CLOUD_SECRET_KEY',
    cloud=True)


# Get bulk closed tasks
task_dict = {}
page = 0
keep_call = True
while keep_call:
    url = "https://api.clickup.com/api/v2/team/{}/task?statuses[]=closed&project_ids[]={}&page={}".format(team_id,
                                                                                                          project_id,
                                                                                                          page)
    response = requests.get(url, headers=headers)
    data = response.json()
    results = data['tasks']
    if len(results) > 0:
        for task in results:
            task_dict[task['id']] = {
                'name': task['name'],
                'url': task['url']
            }
        page += 1
    else:
        keep_call = False
total = len(task_dict.keys())


# Get em7pp attachments with task ID
attachment_dict = {}
manual_attachments = []
retry_collection = []
pptask_list = []
count = 0
for task_id in task_dict.keys():
    count += 1
    print(f"Checking {task_id} ({count} out of {total})")
    url = "https://api.clickup.com/api/v2/task/" + task_id + "/comment"
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        if len(task_has_attachment(data)) > 0:
            attachments = get_attachments(data, attachment_blacklist)
            if len(attachments) > 0:
                attachment_dict[task_id] = attachments
            else:
                manual_attachments.append(task_id)
            pptask_list.append(task_id)
            print("================PowerPack found in " + task_id + "================")
    except NewConnectionError:
        print("Cannot connect to server. Wait 60 seconds")
        retry_collection.append(task_id)
        time.sleep(60)


# Download files to local directory\
# Note there's a download limit (32 files)
base_path = "PATH_TO_LOCAL_DIRECTORY"
for task_id, attachments in attachment_dict.items():
    clean_name = task_dict[task_id]['name'].replace(":", "").replace("\"", "").replace("\n", "")
    dir_path = base_path + "/" + clean_name + " (" + task_id + ")"
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    for attachment in attachments:
        filepath = dir_path + "/" + attachment.split("/")[-1]
        try:
            req = requests.get(attachment)
            with open(filepath, 'wb') as f:
                f.write(req.content)
            print("Saved to " + filepath)
        except ConnectionResetError:
            print("Server side reset connection. Wait 60 seconds")
            time.sleep(60)


# Create a JIRA issue for every task ID
dir_list = os.listdir(base_path)
for solution in dir_list:
    task_id = solution.split("(")[-1].split(")")[0]
    task_name = solution.split("(")[0].strip()
    descript = """
                Task: %s
                Link: %s
                """ % (task_name, task_dict[task_id]['url'])
    fields = {
        'project': {'key': 'PTAC'},
        'summary': task_name,
        'description': descript,
        'issuetype': {'name': 'Solution'},
    }
    # Get new JIRA issue ID
    issue_result = jira.issue_create(fields)
    # Get Solution files
    solution_path = base_path + "/" + solution
    attachment_list = os.listdir(solution_path)
    for attachment in attachment_list:
        attachment_path = solution_path + "/" + attachment
        jira.add_attachment(issue_result['key'], attachment_path)
        print("Attachment Added: " + attachment_path)
    count += 1