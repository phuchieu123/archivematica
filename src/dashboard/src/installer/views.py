# This file is part of Archivematica.
#
# Copyright 2010-2013 Artefactual Systems Inc. <http://artefactual.com>
#
# Archivematica is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Archivematica is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Archivematica.  If not, see <http://www.gnu.org/licenses/>.

from django.conf import settings as django_settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from main.models import Agent
from installer.forms import SuperUserCreationForm
from tastypie.models import ApiKey
import components.helpers as helpers
from components.administration.views import administration_render_storage_directories_to_dicts

import sys
sys.path.append("/usr/lib/archivematica/archivematicaCommon/utilities")
import FPRClient.main as FPRClient
import storageService as storage_service

import json
import logging
import requests_1_20 as requests
import socket
import uuid

logger = logging.getLogger(__name__)
logging.basicConfig(filename="/tmp/archivematica.log", 
    level=logging.INFO)

def welcome(request):
    # This form will be only accessible when the database has no users
    if 0 < User.objects.count():
        return HttpResponseRedirect(reverse('main.views.home'))
    # Form
    if request.method == 'POST':
        
        # assign UUID to dashboard
        dashboard_uuid = str(uuid.uuid4())
        helpers.set_setting('dashboard_uuid', dashboard_uuid)
        
        # save organization PREMIS agent if supplied
        org_name       = request.POST.get('org_name', '')
        org_identifier = request.POST.get('org_identifier', '')

        if org_name != '' or org_identifier != '':
            agent = Agent.objects.get(pk=2)
            agent.name            = org_name
            agent.identifiertype  = 'repository code'
            agent.identifiervalue = org_identifier
            agent.save()

        # Save user and set cookie to indicate this is the first login
        form = SuperUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            api_key = ApiKey.objects.create(user=user)
            api_key.key = api_key.generate_key()
            api_key.save()
            user = authenticate(username=user.username, password=form.cleaned_data['password1'])
            if user is not None:
                login(request, user)
                request.session['first_login'] = True
                return HttpResponseRedirect(reverse('installer.views.fprconnect'))
    else:
        form = SuperUserCreationForm()

    return render(request, 'installer/welcome.html', {
        'form': form,
      })

def get_my_ip():
    server_addr = '1.2.3.4'
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect((server_addr, 9))
        client = s.getsockname()[0]
    except socket.error:
        client = "1.1.1.1"
    finally:
        del s
    return client
    
def fprconnect(request):
    if request.method == 'POST':
        return HttpResponseRedirect(reverse('installer.views.storagesetup'))
    else:
        return render(request, 'installer/fprconnect.html')

def fprupload(request):
    response_data = {} 
    agent = Agent.objects.get(pk=2)
    url = django_settings.FPR_URL + 'Agent/'
    #url = 'https://fpr.archivematica.org/fpr/api/v1/Agent/' 
    payload = {'uuid': helpers.get_setting('dashboard_uuid'), 
               'agentType': 'new install', 
               'agentName': agent.name, 
               'clientIP': get_my_ip(), 
               'agentIdentifierType': agent.identifiertype, 
               'agentIdentifierValue': agent.identifiervalue
              }
    headers = {'Content-Type': 'application/json'}
    try: 
        r = requests.post(url, data=json.dumps(payload), headers=headers, timeout=10, verify=True)
        if r.status_code == 201:
            response_data['result'] = 'success'
        else:
            response_data['result'] = 'failed to fetch from ' + url
    except:
        response_data['result'] = 'failed to post to ' + url   
 
    return HttpResponse(json.dumps(response_data), content_type="application/json")            

def fprdownload(request):
    response_data = {}

    try:
        fpr = FPRClient.FPRClient(django_settings.FPR_URL)
        myresponse = fpr.getUpdates()
        response_data['response'] = myresponse
        response_data['result'] = 'success'
    except:
        response_data['response'] = 'unable to connect to FPR Server'
        response_data['result'] = 'failed'
     
    myresult = json.dumps(response_data)

    return HttpResponse(myresult, mimetype='application/json')

def storagesetup(request):
    if request.method == 'POST':
        helpers.set_setting('storage_service_url', 'http://localhost:8000')
        if "use_default" in request.POST:
            default_space = "/"
            # TODO get value of %sharedPath%, and add wwww/AIPsStore/
            default_aip_storage = 'var/archivematica/sharedDirectory/www/AIPsStore/'
            description = 'Store AIP in standard Archivematica Directory'
            logging.info("Using default values for storage service; space: {}; AIP storage: {}".format(default_space, default_aip_storage))
            # Create pipeline
            try:
                storage_service.create_pipeline()
            except:
                # TODO: make this pretty
                return HttpResponse('Error creating pipeline: is the storage server running? Please contact administrator.')
            # Check if default space already exists, create if it doesn't
            space = storage_service.get_space(access_protocol="FS", path=default_space)
            if len(space) < 1:
                space = storage_service.create_space(default_space, "FS")
            else:
                space = space[0]
            # Create default AIP storage
            if not storage_service.get_location(purpose="AS",
                                        path=default_aip_storage,
                                        space=space):
                storage_service.create_location(purpose="AS",
                                        path=default_aip_storage,
                                        space=space,
                                        description=description)
            # Create currently processing location
            if not storage_service.get_location(purpose="CP",
                                        space=space):
                storage_service.create_location(purpose="CP",
                                        path=".",
                                        space=space)
        # Initial setup of storage directories MicroServiceChoiceReplacementDic
        administration_render_storage_directories_to_dicts()
        return HttpResponseRedirect(reverse('main.views.home'))
    else:
        return render(request, 'installer/storagesetup.html', locals())
