#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
import sys, os, json
from slugify import slugify
import magic
from exchangelib import FileAttachment, ItemAttachment, Message

class TempAttachment:
    'class for file type detection and extraction of EWS attachment'

    def __init__(self, EWS_attachment):

        self.logger = logging.getLogger('workflows.' + __name__)
        
        #the EWS_attachment is a <class 'exchangelib.attachments.FileAttachment'>
        self.EWS_attachment = EWS_attachment
        #FileAttachment(attachment_id=AttachmentId(
        #    'AAMkAGRkNzU1M2NlLWY1ZDQtNDA1Ny05YWY2LWZiNDE2NTA5ODI3NwBGAAAA
        #    AAC2yKUJwj5ZT5oFtXmylSweBwBcLk7i5hPXSoCrucs14LPhAABYI+QKAABcL
        #    k7i5hPXSoCrucs14LPhAABYI/fsAAABEgAQAIsgOuatoAlFkaCX9qxmXZU=',
        #     None, None),
        #     name='ip.txt',
        #     content_type=None,
        #     content_id=None,
        #     content_location=None,
        #     size=6294,
        #     last_modified_time=EWSDateTime(2017, 3, 10, 16, 32, 6,
        #     tzinfo=<DstTzInfo 'Europe/Zurich' CET+1:00:00 STD>),
        #     is_inline=False, is_contact_photo=False)

        self.isFileAttachment = False
        self.isInline = self.EWS_attachment.is_inline 
        self.isEmailAttachment = False
        #if the initial attachment is an email
        #it may also have attachment, like 2nd level of attachment
        #all second level of attachments are put in the below list
        self.attachments = list()

        if isinstance(self.EWS_attachment, FileAttachment):
            self.isFileAttachment = True

        if isinstance(self.EWS_attachment, ItemAttachment):
            if isinstance(self.EWS_attachment.item, Message):
                self.isEmailAttachment = True
                #try:
                #the attachment has attachment itself
                for attachment in self.EWS_attachment.item.attachments:
                    self.attachments.append(attachment)
                #except AttributeError:
                #    #the attachment does not have attachment
                #    pass
        if self.isFileAttachment:
            self.filetype = self.getFileType()
        else:
            #can't get the raw content if it is an ItemAttachment
            #so getting file type is not possible
            self.filetype = 'ItemAttachment'
        self.filename = self.getFilename()
        self.filepath = '/tmp/' + self.filename
        
    def getFileType(self):
        self.logger.info('%s.getFileType starts', __name__)
        mime = magic.Magic(mime = True)
        #using the first 11 bytes to check the mime-type
        self.filetype = mime.from_buffer(self.EWS_attachment.content[0:10])
        return self.filetype
            
    def getFilename(self):
        self.logger.info('%s.getFileName starts', __name__)
        #by default the filename is untitled
        #anticipating the case where no email subject
        filename = 'Untitled'
        if self.isFileAttachment:
            filename = self.EWS_attachment.name
        elif self.isEmailAttachment:
            #the email attachment will be write to disk as eml
            #as filename, we use the email subject
            filename = self.EWS_attachment.item.subject

            #making the filename ok (no special char etc...)
            filename = slugify(filename)
            #adding eml extension
            filename += '.eml'

        return filename

    def writeFile(self):
        self.logger.info('%s.writeFile starts', __name__)
        with open(self.filepath, 'wb') as out:
            if self.isFileAttachment:
                #proper file as attachment
                out.write(self.EWS_attachment.content)
            elif self.isEmailAttachment:
                #the attachment is an email
                out.write(self.EWS_attachment.item.mime_content)
        return self.filepath

    def deleteFile(self):
        self.logger.info('%s.deleteFile starts', __name__)
        os.remove(self.filepath)
