#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os, sys
import logging
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = current_dir + '/..'
sys.path.insert(0, current_dir)

from common.common import getConf
from objects.EwsConnector import EwsConnector
from objects.TheHiveConnector import TheHiveConnector
from objects.TempAttachment import TempAttachment

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

    #alternate way to get the body
    #soup = BeautifulSoup(email.body, 'html.parser')
    #try:
    #    #html email
    #    body = soup.body.text
    #except AttributeError:
    #    #non html email
    #    body = soup.text

    return ('```\n' + replyToInfo + body + '\n```')

if __name__ == '__main__':
    connectEws() 
