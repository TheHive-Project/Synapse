#!/usr/bin/env python3
# -*- coding: utf8 -*-

'''
Ews2Case with added functionality to find observables in the email body.
Code for searchObservables, isWhitelisted, and loadWhitelists taken
directly from https://github.com/xme/dockers/tree/master/imap2thehive
All credit to the original functions goes to Xme
'''

from bs4 import BeautifulSoup
import os, sys
import logging
import re
import time
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = current_dir + '/..'
sys.path.insert(0, current_dir)

from common.common import getConf
from objects.EwsConnector import EwsConnector
from objects.TheHiveConnector import TheHiveConnector
from objects.TempAttachment import TempAttachment

from thehive4py.api import TheHiveApi
from thehive4py.models import Case, CaseTask, CaseObservable, CustomFieldHelper
from thehive4py.models import Alert, AlertArtifact

#Location of whitelist file
WHITELIST = '/home/thehive/Synapse/Synapse/workflows/objects/thehive.whitelist'
#Example contents of thehive.whitelist
'''
\.domain\.com
.domain.com
domain.com
172\.16\.\d{1,3}\.\d{1,3}
192\.168\.\d{1,3}\.\d{1,3}
'''
#List to hold contents from whitelist file
whitelists = []

#TheHive Api key
API_KEY = '******'

def connectEws():
    logger = logging.getLogger(__name__)
    logger.info('%s.connectEws starts', __name__)

    report = dict()
    report['success'] = bool()

    try:
        cfg = getConf()
        ewsConnector = EwsConnector(cfg)
        folder_name = cfg.get('EWS', 'folder_name')
        unread = ewsConnector.scan(folder_name)

        theHiveConnector = TheHiveConnector(cfg)       

        api = TheHiveApi('http://127.0.0.1:9000', API_KEY)

        for msg in unread:
            #type(msg)
            #<class 'exchangelib.folders.Message'>
            conversationId = msg.conversation_id.id
            
            #searching if case has already been created from the email
            #conversation
            esCaseId = theHiveConnector.searchCaseByDescription(conversationId)

            if esCaseId is None:
                #no case previously created from the conversation
                caseTitle = str(msg.subject)
                caseDescription = ('```\n' +
                    'Case created by Synapse\n' +
                    'conversation_id: "' +
                    str(msg.conversation_id.id) +
                    '"\n' +
                    '```')
                if msg.categories:
                    assignee = msg.categories[0]
                else:
                    assignee = 'synapse'

                case = theHiveConnector.craftCase(caseTitle, caseDescription)
                createdCase = theHiveConnector.createCase(case)
                caseUpdated = theHiveConnector.assignCase(createdCase, assignee)

                commTask = theHiveConnector.craftCommTask()
                esCaseId = caseUpdated.id
                commTaskId = theHiveConnector.createTask(esCaseId, commTask)

            else:
                #case previously created from the conversation
                commTaskId = theHiveConnector.getTaskIdByTitle(
                    esCaseId, 'Communication')

                if commTaskId != None:
                    pass
                else:
                    #case already exists but no Communication task found
                    #creating comm task
                    commTask = theHiveConnector.craftCommTask()
                    commTaskId = theHiveConnector.createTask(esCaseId, commTask) 

            
            fullBody = getEmailBody(msg)
            
            #Scan body message for observables, returns list of observables
            observables = searchObservables(fullBody)

            taskLog = theHiveConnector.craftTaskLog(fullBody)
            createdTaskLogId = theHiveConnector.addTaskLog(commTaskId, taskLog)

            readMsg = ewsConnector.markAsRead(msg)

            for attachmentLvl1 in msg.attachments:
                #uploading the attachment as file observable
                #is the attachment is a .msg, the eml version
                #of the file is uploaded
                tempAttachment = TempAttachment(attachmentLvl1)

                if not tempAttachment.isInline:
                    #adding the attachment only if it is not inline
                    #inline attachments are pictures in the email body
                    tmpFilepath = tempAttachment.writeFile()
                    to = str()
                    for recipient in msg.to_recipients:
                        to = to + recipient.email_address + ' ' 
                    comment = 'Attachment from email sent by '
                    comment += str(msg.author.email_address).lower()
                    comment += ' and received by '
                    comment += str(to).lower()
                    comment += ' with subject: <'
                    comment += msg.subject
                    comment += '>'
                    theHiveConnector.addFileObservable(esCaseId,
                        tmpFilepath,
                        comment)

                    if tempAttachment.isEmailAttachment:
                        #if the attachment is an email
                        #attachments of this email are also
                        #uploaded to TheHive
                        for attachmentLvl2 in tempAttachment.attachments:
                            tempAttachmentLvl2 = TempAttachment(attachmentLvl2)
                            tmpFilepath = tempAttachmentLvl2.writeFile()
                            comment = 'Attachment from the email attached'
                            theHiveConnector.addFileObservable(esCaseId,
                                tmpFilepath,
                                comment)
            #Parse obserables
            for o in observables:
                if isWhitelisted(o['value']):
                    print("skipping %s" % o['value'])
                else:
                    observable = CaseObservable(
                        dataType = o['type'],
                        data = o['value'],
                        tlp = 2,
                        ioc = False,
                        tags=['Synapse'],
                        message = 'Found in the email body'
                        )
                    #send observables to case
                    response = api.create_case_observable(esCaseId, observable)
                    time.sleep(1)
        report['success'] = True
        return report

    except Exception as e:
            logger.error('Failed to create case from email', exc_info=True)
            report['success'] = False
            return report
            

def getEmailBody(email):
    #crafting some "reply to" info
    #From
    #Sent
    #To
    #Cc
    #Subject

    to = str()
    #making sure that there is a recipient
    #because cannot iterate over None object
    if email.to_recipients:
        for recipient in email.to_recipients:
            to = to + recipient.email_address + ' ' 
    else:
        to = ''

    replyToInfo = ('From: ' + str(email.author.email_address).lower() + '\n' +
        'Sent: ' + str(email.datetime_sent) + '\n' +
        'To: ' + to.lower() + '\n' +
        'Cc: ' + str(email.display_cc).lower() + '\n' +
        'Subject: ' + str(email.subject) + '\n\n') 

    body = email.text_body
    #email.text_body should get the body either it is
    #html or raw text
    #unfortunately it is only supported with Exchange 2013
    #so we need to get the body from another way

    if body is None:
        #alternate way to get the body
        soup = BeautifulSoup(email.body, 'html.parser')
        try:
            #html email
            body = soup.body.text
        except AttributeError:
            #non html email
            body = soup.text

    return ('```\n' + replyToInfo + str(body) + '\n```')

def searchObservables(body):

    observables = []
    # Observable types
    # Source: https://github.com/armbues/ioc_parser/blob/master/iocp/data/patterns.ini
    observableTypes = [
         { 'type': 'filename', 'regex': r'\b([A-Za-z0-9-_\.]+\.(exe|dll|bat|sys|htm|html|js|jar|jpg|png|vb|scr|pif|chm|zip|rar|cab|pdf|doc|docx|ppt|pptx|xls|xlsx|swf|gif))\b' },
         { 'type': 'url',      'regex': r'\b([a-z]{3,}\:\/\/[a-z0-9.\-:/?=&;]{16,})\b' },
         { 'type': 'ip',       'regex': r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b' },
         { 'type': 'fqdn',     'regex': r'\b(([a-z0-9\-]{2,}\[?\.\]?){2,}(abogado|ac|academy|accountants|active|actor|ad|adult|ae|aero|af|ag|agency|ai|airforce|al|allfinanz|alsace|am|amsterdam|an|android|ao|aq|aquarelle|ar|archi|army|arpa|as|asia|associates|at|attorney|au|auction|audio|autos|aw|ax|axa|az|ba|band|bank|bar|barclaycard|barclays|bargains|bayern|bb|bd|be|beer|berlin|best|bf|bg|bh|bi|bid|bike|bingo|bio|biz|bj|black|blackfriday|bloomberg|blue|bm|bmw|bn|bnpparibas|bo|boo|boutique|br|brussels|bs|bt|budapest|build|builders|business|buzz|bv|bw|by|bz|bzh|ca|cal|camera|camp|cancerresearch|canon|capetown|capital|caravan|cards|care|career|careers|cartier|casa|cash|cat|catering|cc|cd|center|ceo|cern|cf|cg|ch|channel|chat|cheap|christmas|chrome|church|ci|citic|city|ck|cl|claims|cleaning|click|clinic|clothing|club|cm|cn|co|coach|codes|coffee|college|cologne|com|community|company|computer|condos|construction|consulting|contractors|cooking|cool|coop|country|cr|credit|creditcard|cricket|crs|cruises|cu|cuisinella|cv|cw|cx|cy|cymru|cz|dabur|dad|dance|dating|day|dclk|de|deals|degree|delivery|democrat|dental|dentist|desi|design|dev|diamonds|diet|digital|direct|directory|discount|dj|dk|dm|dnp|do|docs|domains|doosan|durban|dvag|dz|eat|ec|edu|education|ee|eg|email|emerck|energy|engineer|engineering|enterprises|equipment|er|es|esq|estate|et|eu|eurovision|eus|events|everbank|exchange|expert|exposed|fail|farm|fashion|feedback|fi|finance|financial|firmdale|fish|fishing|fit|fitness|fj|fk|flights|florist|flowers|flsmidth|fly|fm|fo|foo|forsale|foundation|fr|frl|frogans|fund|furniture|futbol|ga|gal|gallery|garden|gb|gbiz|gd|ge|gent|gf|gg|ggee|gh|gi|gift|gifts|gives|gl|glass|gle|global|globo|gm|gmail|gmo|gmx|gn|goog|google|gop|gov|gp|gq|gr|graphics|gratis|green|gripe|gs|gt|gu|guide|guitars|guru|gw|gy|hamburg|hangout|haus|healthcare|help|here|hermes|hiphop|hiv|hk|hm|hn|holdings|holiday|homes|horse|host|hosting|house|how|hr|ht|hu|ibm|id|ie|ifm|il|im|immo|immobilien|in|industries|info|ing|ink|institute|insure|int|international|investments|io|iq|ir|irish|is|it|iwc|jcb|je|jetzt|jm|jo|jobs|joburg|jp|juegos|kaufen|kddi|ke|kg|kh|ki|kim|kitchen|kiwi|km|kn|koeln|kp|kr|krd|kred|kw|ky|kyoto|kz|la|lacaixa|land|lat|latrobe|lawyer|lb|lc|lds|lease|legal|lgbt|li|lidl|life|lighting|limited|limo|link|lk|loans|london|lotte|lotto|lr|ls|lt|ltda|lu|luxe|luxury|lv|ly|ma|madrid|maison|management|mango|market|marketing|marriott|mc|md|me|media|meet|melbourne|meme|memorial|menu|mg|mh|miami|mil|mini|mk|ml|mm|mn|mo|mobi|moda|moe|monash|money|mormon|mortgage|moscow|motorcycles|mov|mp|mq|mr|ms|mt|mu|museum|mv|mw|mx|my|mz|na|nagoya|name|navy|nc|ne|net|network|neustar|new|nexus|nf|ng|ngo|nhk|ni|ninja|nl|no|np|nr|nra|nrw|ntt|nu|nyc|nz|okinawa|om|one|ong|onl|ooo|org|organic|osaka|otsuka|ovh|pa|paris|partners|parts|party|pe|pf|pg|ph|pharmacy|photo|photography|photos|physio|pics|pictures|pink|pizza|pk|pl|place|plumbing|pm|pn|pohl|poker|porn|post|pr|praxi|press|pro|prod|productions|prof|properties|property|ps|pt|pub|pw|qa|qpon|quebec|re|realtor|recipes|red|rehab|reise|reisen|reit|ren|rentals|repair|report|republican|rest|restaurant|reviews|rich|rio|rip|ro|rocks|rodeo|rs|rsvp|ru|ruhr|rw|ryukyu|sa|saarland|sale|samsung|sarl|sb|sc|sca|scb|schmidt|schule|schwarz|science|scot|sd|se|services|sew|sexy|sg|sh|shiksha|shoes|shriram|si|singles|sj|sk|sky|sl|sm|sn|so|social|software|sohu|solar|solutions|soy|space|spiegel|sr|st|style|su|supplies|supply|support|surf|surgery|suzuki|sv|sx|sy|sydney|systems|sz|taipei|tatar|tattoo|tax|tc|td|technology|tel|temasek|tennis|tf|tg|th|tienda|tips|tires|tirol|tj|tk|tl|tm|tn|to|today|tokyo|tools|top|toshiba|town|toys|tp|tr|trade|training|travel|trust|tt|tui|tv|tw|tz|ua|ug|uk|university|uno|uol|us|uy|uz|va|vacations|vc|ve|vegas|ventures|versicherung|vet|vg|vi|viajes|video|villas|vision|vlaanderen|vn|vodka|vote|voting|voto|voyage|vu|wales|wang|watch|webcam|website|wed|wedding|wf|whoswho|wien|wiki|williamhill|wme|work|works|world|ws|wtc|wtf|xyz|yachts|yandex|ye|yoga|yokohama|youtube|yt|za|zm|zone|zuerich|zw))\b' },
         { 'type': 'domain',     'regex': r'\b(([a-z0-9\-]{2,}\[?\.\]?){1}(abogado|ac|academy|accountants|active|actor|ad|adult|ae|aero|af|ag|agency|ai|airforce|al|allfinanz|alsace|am|amsterdam|an|android|ao|aq|aquarelle|ar|archi|army|arpa|as|asia|associates|at|attorney|au|auction|audio|autos|aw|ax|axa|az|ba|band|bank|bar|barclaycard|barclays|bargains|bayern|bb|bd|be|beer|berlin|best|bf|bg|bh|bi|bid|bike|bingo|bio|biz|bj|black|blackfriday|bloomberg|blue|bm|bmw|bn|bnpparibas|bo|boo|boutique|br|brussels|bs|bt|budapest|build|builders|business|buzz|bv|bw|by|bz|bzh|ca|cal|camera|camp|cancerresearch|canon|capetown|capital|caravan|cards|care|career|careers|cartier|casa|cash|cat|catering|cc|cd|center|ceo|cern|cf|cg|ch|channel|chat|cheap|christmas|chrome|church|ci|citic|city|ck|cl|claims|cleaning|click|clinic|clothing|club|cm|cn|co|coach|codes|coffee|college|cologne|com|community|company|computer|condos|construction|consulting|contractors|cooking|cool|coop|country|cr|credit|creditcard|cricket|crs|cruises|cu|cuisinella|cv|cw|cx|cy|cymru|cz|dabur|dad|dance|dating|day|dclk|de|deals|degree|delivery|democrat|dental|dentist|desi|design|dev|diamonds|diet|digital|direct|directory|discount|dj|dk|dm|dnp|do|docs|domains|doosan|durban|dvag|dz|eat|ec|edu|education|ee|eg|email|emerck|energy|engineer|engineering|enterprises|equipment|er|es|esq|estate|et|eu|eurovision|eus|events|everbank|exchange|expert|exposed|fail|farm|fashion|feedback|fi|finance|financial|firmdale|fish|fishing|fit|fitness|fj|fk|flights|florist|flowers|flsmidth|fly|fm|fo|foo|forsale|foundation|fr|frl|frogans|fund|furniture|futbol|ga|gal|gallery|garden|gb|gbiz|gd|ge|gent|gf|gg|ggee|gh|gi|gift|gifts|gives|gl|glass|gle|global|globo|gm|gmail|gmo|gmx|gn|goog|google|gop|gov|gp|gq|gr|graphics|gratis|green|gripe|gs|gt|gu|guide|guitars|guru|gw|gy|hamburg|hangout|haus|healthcare|help|here|hermes|hiphop|hiv|hk|hm|hn|holdings|holiday|homes|horse|host|hosting|house|how|hr|ht|hu|ibm|id|ie|ifm|il|im|immo|immobilien|in|industries|info|ing|ink|institute|insure|int|international|investments|io|iq|ir|irish|is|it|iwc|jcb|je|jetzt|jm|jo|jobs|joburg|jp|juegos|kaufen|kddi|ke|kg|kh|ki|kim|kitchen|kiwi|km|kn|koeln|kp|kr|krd|kred|kw|ky|kyoto|kz|la|lacaixa|land|lat|latrobe|lawyer|lb|lc|lds|lease|legal|lgbt|li|lidl|life|lighting|limited|limo|link|lk|loans|london|lotte|lotto|lr|ls|lt|ltda|lu|luxe|luxury|lv|ly|ma|madrid|maison|management|mango|market|marketing|marriott|mc|md|me|media|meet|melbourne|meme|memorial|menu|mg|mh|miami|mil|mini|mk|ml|mm|mn|mo|mobi|moda|moe|monash|money|mormon|mortgage|moscow|motorcycles|mov|mp|mq|mr|ms|mt|mu|museum|mv|mw|mx|my|mz|na|nagoya|name|navy|nc|ne|net|network|neustar|new|nexus|nf|ng|ngo|nhk|ni|ninja|nl|no|np|nr|nra|nrw|ntt|nu|nyc|nz|okinawa|om|one|ong|onl|ooo|org|organic|osaka|otsuka|ovh|pa|paris|partners|parts|party|pe|pf|pg|ph|pharmacy|photo|photography|photos|physio|pics|pictures|pink|pizza|pk|pl|place|plumbing|pm|pn|pohl|poker|porn|post|pr|praxi|press|pro|prod|productions|prof|properties|property|ps|pt|pub|pw|qa|qpon|quebec|re|realtor|recipes|red|rehab|reise|reisen|reit|ren|rentals|repair|report|republican|rest|restaurant|reviews|rich|rio|rip|ro|rocks|rodeo|rs|rsvp|ru|ruhr|rw|ryukyu|sa|saarland|sale|samsung|sarl|sb|sc|sca|scb|schmidt|schule|schwarz|science|scot|sd|se|services|sew|sexy|sg|sh|shiksha|shoes|shriram|si|singles|sj|sk|sky|sl|sm|sn|so|social|software|sohu|solar|solutions|soy|space|spiegel|sr|st|style|su|supplies|supply|support|surf|surgery|suzuki|sv|sx|sy|sydney|systems|sz|taipei|tatar|tattoo|tax|tc|td|technology|tel|temasek|tennis|tf|tg|th|tienda|tips|tires|tirol|tj|tk|tl|tm|tn|to|today|tokyo|tools|top|toshiba|town|toys|tp|tr|trade|training|travel|trust|tt|tui|tv|tw|tz|ua|ug|uk|university|uno|uol|us|uy|uz|va|vacations|vc|ve|vegas|ventures|versicherung|vet|vg|vi|viajes|video|villas|vision|vlaanderen|vn|vodka|vote|voting|voto|voyage|vu|wales|wang|watch|webcam|website|wed|wedding|wf|whoswho|wien|wiki|williamhill|wme|work|works|world|ws|wtc|wtf|xyz|yachts|yandex|ye|yoga|yokohama|youtube|yt|za|zm|zone|zuerich|zw))\b' },
         { 'type': 'mail',   'regex': r'\b([a-z][_a-z0-9-.+]+@[a-z0-9-.]+\.[a-z]+)\b' },
         { 'type': 'hash',   'regex': r'\b([a-f0-9]{32}|[A-F0-9]{32})\b' },
         { 'type': 'hash',   'regex': r'\b([a-f0-9]{40}|[A-F0-9]{40})\b' },
         { 'type': 'hash',   'regex': r'\b([a-f0-9]{64}|[A-F0-9]{64})\b' }
         ]
   
    for o in observableTypes:
        for match in re.findall(o['regex'], body, re.MULTILINE|re.IGNORECASE):
            # Bug: If match is a tuple (example for domain or fqdn), use the 1st element
            
            if type(match) is tuple:
                match = match[0]
            observables.append({ 'type': o['type'], 'value': match })
    
    
    return observables

def loadWhitelists(filename):
    '''
    Read regex from the provided file, validate them and populate the list
    '''
    if not filename:
        return []

    try:
        lines = [line.rstrip('\n') for line in open(filename)]
    except IOError as e:
        log.error('Cannot read %s: %s' % (filename, e.strerror))
        sys.exit(1)

    i = 1
    w = []
    for l in lines:
        if len(l) > 0:
            if l[0] == '#':
                # Skip comments and empty lines
                continue
            try:
                re.compile(l)
            except re.error:
                log.error('Line %d: Regular expression "%s" is invalid.' % (l, f))
                sys.exit(1)
            i += 1
            w.append(l)
    return w

def isWhitelisted(string):
    '''
    Check if the provided string matches one of the whitelist regexes
    '''
    global whitelists
    whitelists = loadWhitelists(WHITELIST)
    found = False
    for w in whitelists:
        if re.search(w, string, re.IGNORECASE):
            found = True
            break
    return found


if __name__ == '__main__':
    connectEws()
