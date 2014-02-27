import re
import logging
import time
import threading
from Queue import Queue
from urlparse import urlparse
import traceback

import requests
import requests_cache
from bs4 import BeautifulSoup

from pyramid.events import subscriber
from pyramid.renderers import render

from h import events
from h.notifier import user_profile_url, standalone_url, AnnotationNotifier

log = logging.getLogger(__name__)


class DocumentOwnerNotificationTemplate(object):
    template = 'h:templates/emails/document_owner_notification.txt'

    @staticmethod
    def _create_template_map(request, annotation):
        tags = '\ntags: ' + ', '.join(annotation['tags']) if 'tags' in annotation else ''
        user = re.search("^acct:([^@]+)", annotation['user']).group(1)
        return {
            'document_title': annotation['title'],
            'document_path': annotation['uri'],
            'text': annotation['text'],
            'tags': tags,
            'user_profile': user_profile_url(request, annotation['user']),
            'user': user,
            'path': standalone_url(request, annotation['id']),
            'timestamp': annotation['created'],
        }

    @staticmethod
    def render(request, annotation):
        return render(DocumentOwnerNotificationTemplate.template,
                      DocumentOwnerNotificationTemplate._create_template_map(request, annotation),
                      request)

    @staticmethod
    def generate_notification(request, annotation, data):
        recipients = [data['email']]
        rendered = DocumentOwnerNotificationTemplate.render(request, annotation)
        subject = "New annotation in your page: " + annotation['title'] + \
                  " (" + annotation['uri'] + ")"
        return {
            'status': True,
            'recipients': recipients,
            'rendered': rendered,
            'subject': subject
        }

AnnotationNotifier.register_template('document_owner', DocumentOwnerNotificationTemplate.generate_notification)

requests_cache.install_cache('document_cache')
document_cache = {}
notifications = Queue()


def notification_worker():
    while True:
        if not notifications.empty():
            try:
                annotation, notification, notifier = notifications.get()
                uri = annotation['uri']
                r = requests.get(uri)
                for k in r.headers:
                    log.info(k + ': ' + r.headers[k])
                page_date = r.headers['last-modified'] if 'last-modified' in r.headers else r.headers['date']

                # Check if the page is not cached or the cache is old
                if uri not in document_cache or document_cache[uri]['date'] != page_date:
                    parsed_data = BeautifulSoup(r.text)
                    documents = parsed_data.select('a[rel="reply-to"]')
                    hrefs = []
                    for d in documents:
                        if d['href'].lower()[0:7] == 'mailto:': hrefs.append(d['href'][7:])
                        else: hrefs.append(d['href'])
                    document_cache[uri] = {
                        'date': page_date,
                        'hrefs': hrefs
                    }

                # Now send the notifications
                emails = document_cache[uri]['hrefs']
                url_struct = urlparse(annotation['uri'])
                domain = url_struct.hostname if len(url_struct.hostname) > 0 else url_struct.path
                if domain[0:4] == 'www.': domain = domain[4:]
                for email in emails:
                    # Domain matching
                    mail_domain = email.split('@')[-1]
                    if mail_domain == domain:
                        # Send notification to owners
                        notification['recipients'] = [email]
                        notifier.send_rendered_notification(notification)
                notifications.task_done()
            except:
                log.error(traceback.format_exc())
                log.error('Notification_worker error!')
        else:
            time.sleep(1)


@subscriber(events.AnnotationEvent)
def domain_notification(event):
    log.info('event!!!!')
    if event.action == 'create':
        # We have to render our template here,
        # because the other thread does not see all pyramid stuff
        notification = DocumentOwnerNotificationTemplate.generate_notification(
            event.request, event.annotation, {'email': ''}
        )
        notifier = AnnotationNotifier(event.request)
        notifications.put((event.annotation, notification, notifier))


def create_thread():
    worker = threading.Thread(target=notification_worker)
    worker.daemon = True
    worker.start()


def includeme(config):
    create_thread()
    config.scan(__name__)