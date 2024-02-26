#!/usr/bin/env python3

# Author: 3V1LC47 <b900613@gmail.com>
# You need to install telethon (and cryptg to speed up downloads)

from os import getenv, path
from shutil import move
from retry import retry
import subprocess
import math
import time
from datetime import datetime, timedelta, timezone
import random
import string
import os.path
import hashlib
from mimetypes import guess_extension
import re

from sessionManager import getSession, saveSession

import telethon.sync
from telethon import TelegramClient,utils, events, __version__
from telethon.tl.types import PeerChannel,PeerChat,PeerUser, DocumentAttributeFilename, DocumentAttributeVideo, InputDocument
#from telethon.tl.functions.messages import GetHistory
import logging


logging.basicConfig(format='[%(levelname) 5s/%(asctime)s]%(name)s:%(message)s',
					level=logging.WARNING)

import multiprocessing
import argparse
import asyncio
import numpy
import psutil
import json as json
import sqlite3
import pymssql



TDD_VERSION="1.7.0-3V1LC4T"

TELEGRAM_DAEMON_API_ID = getenv("TELEGRAM_DAEMON_API_ID")
TELEGRAM_DAEMON_API_HASH = getenv("TELEGRAM_DAEMON_API_HASH")
TELEGRAM_DAEMON_CHANNEL = getenv("TELEGRAM_DAEMON_CHANNEL")

TELEGRAM_DAEMON_SESSION_PATH = getenv("TELEGRAM_DAEMON_SESSION_PATH")

TELEGRAM_DAEMON_DEST=getenv("TELEGRAM_DAEMON_DEST", "/telegram-downloads")
TELEGRAM_DAEMON_TEMP=getenv("TELEGRAM_DAEMON_TEMP", "/telegram-downloads-temp")
TELEGRAM_DAEMON_DUPLICATES=getenv("TELEGRAM_DAEMON_DUPLICATES", "rename")

TELEGRAM_DAEMON_TEMP_SUFFIX="tdd"

parser = argparse.ArgumentParser(
	description="Script to download files from a Telegram Channel.")
parser.add_argument(
	"--api-id",
	required=TELEGRAM_DAEMON_API_ID == None,
	type=int,
	default=TELEGRAM_DAEMON_API_ID,
	help=
	'api_id from https://core.telegram.org/api/obtaining_api_id (default is TELEGRAM_DAEMON_API_ID env var)'
)
parser.add_argument(
	"--api-hash",
	required=TELEGRAM_DAEMON_API_HASH == None,
	type=str,
	default=TELEGRAM_DAEMON_API_HASH,
	help=
	'api_hash from https://core.telegram.org/api/obtaining_api_id (default is TELEGRAM_DAEMON_API_HASH env var)'
)
parser.add_argument(
	"--dest",
	type=str,
	default=TELEGRAM_DAEMON_DEST,
	help=
	'Destination path for downloaded files (default is /telegram-downloads).')
parser.add_argument(
	"--temp",
	type=str,
	default=TELEGRAM_DAEMON_TEMP,
	help=
	'Destination path for temporary files (default is using the same downloaded files directory).')
parser.add_argument(
	"--channel",
	required=TELEGRAM_DAEMON_CHANNEL == None,
	type=int,
	default=TELEGRAM_DAEMON_CHANNEL,
	help=
	'Channel id to download from it (default is TELEGRAM_DAEMON_CHANNEL env var'
)
args = parser.parse_args()

api_id = args.api_id
api_hash = args.api_hash
robot_chat_id = args.channel
downloadFolder = args.dest
tempFolder = args.temp
duplicates=args.duplicates
worker_count = multiprocessing.cpu_count()
worker_count = 4
updateFrequency = 30
MSG_transfer_rate = 0.8
lastUpdate = 0
MSG_trans_retry_delay = 8
MSG_trans_retry_limit = 3
actionlock_release_interval = 0.3
hash_chunk_size = 16384  # Adjust the chunk size as needed
#multiprocessing.Value('f', 0)


time_a = time.time()


if not tempFolder:
	tempFolder = downloadFolder

# Edit these lines:
proxy = None

# End of interesting parameters

status_msg = []
status_update_time = time.time()
in_progress={}
msg_queue_L = asyncio.Queue()
msg_queue_H = asyncio.Queue()
error_count = 0
ignore_forward_list = []
GT_list = []
GT_list_B = []
auto_forward_list = []
auto_forward_list_B=[]
RC_list = []
RC_list_B = []
file_hash_list_md5 = []
file_hash_list_sha256 = []
message_record_list = []
file_duplicate_count = 0
extra_AF_list=[]
DB_info=[]
DB_conn=[]
RC_chat_id = 0
file_drive_entity = []
RC_entity = []
ID_NAME = {}

async def sendHelloMessage(client, robot_chat):
	entity = await client.get_entity(robot_chat)
	print("Telegram Download Daemon "+TDD_VERSION+" using Telethon "+__version__)
	await client.send_message(entity, "Telegram Download Daemon "+TDD_VERSION+" using Telethon "+__version__)
	await client.send_message(entity, "Hi! Ready for your files!")

@retry(tries=10,delay=8)
async def send_reply(event,msg):
	
	message=await event.reply(msg)
	return message

def getRandomId(len):
	chars=string.ascii_lowercase + string.digits
	return  ''.join(random.choice(chars) for x in range(len))
 
def getFilename(event: events.NewMessage.Event):
	mediaFileName = "unknown"

	if hasattr(event.media, 'photo'):
		mediaFileName = str(event.media.photo.id)+".jpeg"
	elif hasattr(event.media, 'document'):
		for attribute in event.media.document.attributes:
			if isinstance(attribute, DocumentAttributeFilename): 
				mediaFileName=attribute.file_name
				break	 
			if isinstance(attribute, DocumentAttributeVideo):
				# if event.original_update.message.message != '': 
					# mediaFileName = event.original_update.message.message
				# else:	
					# mediaFileName = str(event.message.media.document.id)
				mediaFileName = str(event.message.media.document.id)
				mediaFileName+=guess_extension(event.message.media.document.mime_type)	
	 
	mediaFileName="".join(c for c in mediaFileName if c.isalnum() or c in "()._- ")
	  
	return mediaFileName

def getFilename2(message):
	mediaFileName = "unknown"
	try:
		if hasattr(message.media, 'photo'):
			mediaFileName = str(message.media.photo.id)+".jpeg"
		elif hasattr(message.media, 'document'):
			for attribute in message.media.document.attributes:
				if isinstance(attribute, DocumentAttributeFilename): 
				  mediaFileName=attribute.file_name
				  break	 
				if isinstance(attribute, DocumentAttributeVideo):
				  mediaFileName = str(message.media.document.id)
				  mediaFileName+=guess_extension(message.media.document.mime_type)	
		 
		mediaFileName="".join(c for c in mediaFileName if c.isalnum() or c in "()._- ")
	except Exception as e:
		mediaFileName = str(round(time.time() * 1000))+".???"
	  
	return mediaFileName

async def set_progress(filename, message, received, total):
	global lastUpdate
	global updateFrequency
	global msg_queue_L

	if received >= total:
		try: in_progress.pop(filename)
		except: pass
		return
	percentage = math.trunc(received / total * 10000) / 100

	progress_message= "{0} % ({1} / {2})".format(percentage, received, total)
	in_progress[filename] = progress_message

	currentTime=time.time()
	if (currentTime - lastUpdate) > updateFrequency:
		#await log_reply(message, progress_message)
		await msg_queue_L.put([1,message, progress_message])
		lastUpdate=currentTime
		#await asyncio.sleep(1)
def save_state():
	global GT_list
	global GT_list_B
	global auto_forward_list
	global auto_forward_list_B
	global file_hash_list_md5
	global file_hash_list_sha256
	global message_record_list
	global extra_AF_list
	global DB_info
	global RC_list
	global RC_list_B
	global RC_chat_id
	global ID_NAME
	
	try:
		auto_forward_list_id = []

		save_lst = []
		save_lst.append([])
		save_lst.append([])
		save_lst.append([])
		save_lst.append([])
		save_lst.append([])
		save_lst.append([])
		save_lst.append([])
		save_lst.append(extra_AF_list)
		save_lst.append(DB_info)
		save_lst.append([])
		save_lst.append([])
		save_lst.append(RC_chat_id)
		save_lst.append([])
		
		data = json.dumps(save_lst)
		with open("TG_auto_save.json", 'w') as f:
			json.dump(data, f, ensure_ascii=False, indent=4)
		print("save state sucess")
	except Exception as e:
		print('save operation',str(e))

client = TelegramClient(getSession(), api_id, api_hash,proxy=proxy,auto_reconnect=True,retry_delay= 60,connection_retries= 99999999)

with client:

	saveSession(client.session)

	queue = asyncio.Queue()
	missing_msg_queue = asyncio.Queue()
	GT_queue = asyncio.Queue()
	
	last_msg_id = 0
	RC_chat_last_id = 0
	
	robot_chat = PeerChannel(robot_chat_id)
	
	
	
	afd_event_lock = asyncio.Lock()
	# RC_event_lock = asyncio.Lock()
	hasher_lock = asyncio.Lock()
	afd_list_lock = asyncio.Lock()
	GT_list_lock = asyncio.Lock()
	RC_list_lock = asyncio.Lock()
	EXT_list_lock = asyncio.Lock()
	API_action_lock = asyncio.Lock()
	initail_lock = asyncio.Lock()
	event_handle_lock = asyncio.Lock()
	concurrent_sys_lock = asyncio.Lock()
	statistics_lock = asyncio.Lock()
	afd_handler_lock = asyncio.Lock()
	downloader_lock_norm = asyncio.Lock()
	downloader_lock_GT = asyncio.Lock()
	downloader_lock_pre = asyncio.Lock()
	msg_fill_lock = asyncio.Lock()
	DB_action_lock = asyncio.Lock()
	reply_history_lock = asyncio.Lock()
	
	file_KEY_transfer_lock = 0
	
	RC_mfd_lock = asyncio.Lock()
	
	
	bot_chat_event_history =[]
	
	concurrent_event_handle_count = []
	concurrent_max_handle = 5
	
	handler_statistics=[0,0,0,0,0,0,0,0,0]
	handler_statistics_done=[0,0,0,0,0,0,0,0,0]
	
	status_refresh_req_flag =False
	
	debug_mode = False
	
	GT_pause = False
	tasks = []
	
	me_id = -1
	me_id_full = []
	
	reply_history = []
	
	# @client.on(events.ChatAction)
	# async def action_handler(event):
		# pass
	
	@client.on(events.MessageEdited)
	async def edit_message_handler(event):
		global RC_list
		global RC_list_B
		global RC_chat_id
		global RC_entity
		global ID_NAME
		global handler_statistics
		global handler_statistics_done
		
		await initail_lock.acquire()
		initail_lock.release()
		
		#handler statistics
		await statistics_lock.acquire()
		try:
			handler_statistics[7]+=1
		except:
			print("handler_statistics error at add 0")
		finally:
			statistics_lock.release()
		#print('Message', event.id, 'changed at', event.date)
		try:
			
			
				
			TOID = await peer_to_id(event.to_id)
			RCID = int(TOID)
			if RCID in RC_list:
				date = event.date
				event_type = "edit_message"
				msg_id = event.id
				msg = event.message.message
				sender_id =""
				await API_action_lock.acquire()
				try:
					sender_id = (await event.get_sender()).id
				finally:
					await asyncio.sleep(actionlock_release_interval/2)
					API_action_lock.release()
				from_name = ""
				if await check_id_name_db(str(sender_id)):
					from_name = (await get_id_name_db(str(sender_id)))[0]
				else:	
					from_name = str(await get_display_name_from_id(int(str(sender_id))))
					if from_name is None:
						from_name = "DeletedUser"
						await write_id_name_db(str(sender_id),"DeletedUser")
					else:
						await write_id_name_db(str(sender_id),from_name)
					
				topic =""
				if event.reply_to:
					if event.reply_to.forum_topic:
						if str(event.reply_to.reply_to_top_id)=="None":
							topic = event.reply_to.reply_to_msg_id
						else:
							topic = event.reply_to.reply_to_top_id
					else:
						topic = ""
				else:
					topic = ""
					
				msg_type = "msg"
				document_id = -1
				
				await add_new_msg(RCID,date,event_type,msg_id,sender_id,from_name,topic,msg_type,msg,document_id)
			
			
		except Exception as e:
			if "int() argument must be a string, a bytes-like object or a real number, not " in str(e):
				pass
			else:
				print('event edit handle -level 0.a',str(e))
		finally:
			pass
		
		#handler statistics
		await statistics_lock.acquire()
		try:
			handler_statistics[7]-=1
			handler_statistics_done[7]+=1
		except:
			print("handler_statistics error at del 0")
		finally:
			statistics_lock.release()
		
	@client.on(events.MessageDeleted)
	async def on_delete_message_handler(event):
		global RC_list
		global RC_list_B
		global RC_chat_id
		global RC_entity
		
		
		
		
		offset = timedelta(hours=8, minutes=00)
		current_time = datetime.now(timezone(offset))
		
		await initail_lock.acquire()
		initail_lock.release()
		
		#handler statistics
		await statistics_lock.acquire()
		try:
			handler_statistics[8]+=1
		except:
			print("handler_statistics error at add 0")
		finally:
			statistics_lock.release()
			
		if_hidden_user = False
		
		try:
			
			if event.chat_id == None:
				return 0 
			
			await API_action_lock.acquire()
			try:
				peer_entity = await client.get_input_entity(int(event.chat_id))
				
			except Exception as e:
				if "int() argument must be a string, a bytes-like object or a real number, not 'NoneType'" in str(e):
					pass
				elif "Could not find the input entity for" in str(e):
					try:
						if_hidden_user = True
						TOID = int(str(e).split("=")[1].replace(")"))
					except:
						return 0
				else:
					print('event delete handle -level 0.a',str(e))
			finally:
				API_action_lock.release()
				
			if if_hidden_user:
				pass
			else:
				try:
					TOID  = PeerChannel(peer_entity.channel_id)
				except:
					try:
						TOID  = PeerChat(peer_entity.chat_id)
					except:
						TOID  = PeerUser(peer_entity.user_id)
							
				TOID = await peer_to_id(await get_actual_peer_from_peer(TOID))
			
			# TOID  = utils.get_peer_id(peer_entity)
			RCID = int(TOID)
			
			if RCID in RC_list:
				for msg_id in event.deleted_ids:
					await add_new_msg(RCID,current_time,"del_msg",msg_id,"","","","msg","",-1)
		except Exception as e:
			if "int() argument must be a string, a bytes-like object or a real number, not " in str(e):
				pass
			elif "local variable 'channel_entity' referenced before assignment" in str(e) :
				pass
			else:
				print('event delete handle -level 0.b',str(e))
			
		finally:
			pass
			
		#handler statistics
		await statistics_lock.acquire()
		try:
			handler_statistics[8]-=1
			handler_statistics_done[8]+=1
		except:
			print("handler_statistics error at del 0")
		finally:
			statistics_lock.release()
	
	@client.on(events.NewMessage())
	async def on_new_message_handler(event):
		global time_a
		global error_count
		global status_msg
		global last_msg_id
		global GT_list
		global GT_list_B
		global GT_pause
		global auto_forward_list
		global auto_forward_list_B
		global file_duplicate_count
		global file_hash_list_md5
		global file_hash_list_sha256
		global message_record_list
		global tasks
		global extra_AF_list
		global concurrent_event_handle_count
		global concurrent_max_handle
		global handler_statistics
		global handler_statistics_done
		global status_refresh_req_flag
		global debug_mode
		global bot_chat_event_history
		global DB_info
		global RC_list
		global RC_list_B
		global RC_chat_id
		global RC_entity
		global ID_NAME
		global ignore_forward_list
		
		# print("recieve Msg ID: "+str(event.message.id))
		# print(event.sender_id)
		# print(event.to_id)
		
		level0_error = False
		is_user = False
		
		
		try:
			if event.to_id == robot_chat:
				bot_chat_event_history.append(int(event.message.id))
		except:
			pass
		finally:
			pass
		
		await initail_lock.acquire()
		initail_lock.release()
		
		while len(concurrent_event_handle_count) >concurrent_max_handle:
			await concurrent_sys_lock.acquire()
			try:
				await asyncio.sleep(1)
				concurrent_max_handle = min(concurrent_max_handle+1,1000000000)
			except:
				pass
			finally:
				concurrent_sys_lock.release()
		await event_handle_lock.acquire()
		try:
			#concurrent_event_handle_count.append(str(event.to_id)+"->"+str(event.message.id))
			concurrent_event_handle_count.append([])
		except:
			pass
		finally:
			event_handle_lock.release()
		
		#handler statistics
		await statistics_lock.acquire()
		try:
			handler_statistics[0]+=1
		except:
			print("handler_statistics error at add 0")
		finally:
			statistics_lock.release()
		
		try:
			_ = event.to_id.user_id
			is_user = True
		except:
			is_user = False
		
		try:
			TOID = 0
			if is_user :
				TOID = event.sender_id
				TOID_full = await get_actual_peer(event.sender_id)
			else:
				try:
					TOID = await peer_to_id(event.to_id)
				except:
					pass
				if TOID == 0:
					TOID = int(str(event.to_id).split("=")[1].replace(")",""))
					print("TOID = "+ str(TOID))
					
				TOID_full = event.to_id
		except Exception as e:
			level0_error=True
			if "int() argument must be a string, a bytes-like object or a real number, not " in str(e):
				pass
			else:
				print('event handle -level 0.a',str(e))
		
		
		
		try:
			if level0_error:
				pass
			elif event.to_id == robot_chat:
				
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[1]+=1
				except:
					print("handler_statistics error at add 1")
				finally:
					statistics_lock.release()
					
				#await msg_fill_lock.acquire()
				try:
					# bot_chat_event_history.append(int(event.message.id))
					if last_msg_id != 0 and int(event.message.id) != (last_msg_id+1) and int(event.message.id) > last_msg_id:
						for i in range(last_msg_id+1,int(event.message.id)):
							if i in bot_chat_event_history ==False:
								await missing_msg_queue.put(i)
								bot_chat_event_history.append(i)
					last_msg_id = int(event.message.id)
				except:
					pass
				finally:
					#msg_fill_lock.release()
					pass
				
				
				try:

					if (not event.media) and event.message:
						command = str(event.message.message)
						command = command.lower()
						output = "Unknown command"
						
						if_send =False

						if command == "list":
							try:
								output = subprocess.run(["ls -l "+downloadFolder], shell=True, stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.decode('utf-8')
							except:
								output = "list too long to display"
								
							if_send = True
						elif command == "status" or ("status" in command and ("gt" in command or "af" in command or "ext" in command or "rc" in command)):
							try:
								output,output_af,output_gt,output_rc = await get_status(event)
								
								output = "status report:\n------------------------------------------------------------\n"+output
								
								if "af" in command:
									output = output+output_af
								if "gt" in command:
									output = output+output_gt
								if "rc" in command:
									output = output+output_rc
								if "ext" in command:
									output = output+"\n------------------------------------------------------------\nEXT :"
									i=0
									for ext_pair in extra_AF_list:
										output = output +"\n("+str(i)+")"+str(ext_pair[0])+"->"+str(ext_pair[1])
										i+=1
										
								
								#remove old status message
								try:
									status_update_time = time.time()
									for i in range(0,len(status_msg)):
										await msg_queue_L.put([2,robot_chat_id, status_msg[i]])
									status_msg =[]
									status_msg.append(event.message.id)
								except:
									pass
								
								
							except Exception as e:
								output = "Some error occured while checking the status. Retry.("+str(e)+")"
							if_send = True
						elif command == "clean":
							output = "Cleaning "+tempFolder+"\n"
							output+=subprocess.run(["rm "+tempFolder+"/*."+TELEGRAM_DAEMON_TEMP_SUFFIX], shell=True, stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout
							error_count = 0
							
							if_send = True
						elif command == "current":
							pass
						elif command == "checkhis":
							bot_chat_event_history = []
							await pre_forward()
						elif "added to queue" in command:
							output = event.message.message
						elif "ext=" in command:
							from_channel = int((command.split("=")[1]).split(",")[0])
							to_channel = int((command.split("=")[1]).split(",")[1])
							if [from_channel,to_channel] not in extra_AF_list:
								extra_AF_list.append([from_channel,to_channel])
							msg_queue_H.put_nowait([0,event,"EXT AFD set"])
						elif "ext remove=" in command:
							if "," in command.split("=")[1]:
								from_channel = int((command.split("=")[1]).split(",")[0])
								to_channel = int((command.split("=")[1]).split(",")[1])
								if [from_channel,to_channel] in extra_AF_list:
									extra_AF_list.remove([from_channel,to_channel])
							else:
								if len(extra_AF_list) >= int(command.split("=")[1])+1:
									extra_AF_list.pop(int(command.split("=")[1]))
							msg_queue_H.put_nowait([0,event,"EXT AFD remove"])
						elif "afd=" in command:
							await afd_list_lock.acquire()
							try:
								actual_peer =  await get_actual_peer(int(command.split("=",1)[1]))							
								#new_forward_group = int(command.split("=",1)[1])
								new_forward_group = int(str(actual_peer).split("=")[1].replace(")",""))
								if new_forward_group not in auto_forward_list and await check_AF_db(new_forward_group)==False:
									auto_forward_list.append(new_forward_group)
									auto_forward_list_B.append(int(-1))
									await write_AF_db(new_forward_group,await get_display_name_from_id(new_forward_group),-1,me_id)
									msg_queue_H.put_nowait([1,event, "set auto forward sucess: "+str(new_forward_group)])
								else:
									msg_queue_H.put_nowait([1,event, str(new_forward_group)+"already added"])
							except Exception as e:
								msg_queue_H.put_nowait([1,event, "set auto forward fail: "+str(e)])
								print('add auto forward fail: ', str(e))
							finally:
								afd_list_lock.release()
						elif "afd force=" in command:
							await afd_list_lock.acquire()
							try:
								actual_peer =  await get_actual_peer(int(command.split("=",1)[1]))							
								#new_forward_group = int(command.split("=",1)[1])
								new_forward_group = int(str(actual_peer).split("=")[1].replace(")",""))
								if new_forward_group not in auto_forward_list :
									auto_forward_list.append(new_forward_group)
									auto_forward_list_B.append(int(-1))
									if await check_AF_force_db(new_forward_group,me_id)==False:
										await write_AF_db(new_forward_group,await get_display_name_from_id(new_forward_group),-1,me_id)
									msg_queue_H.put_nowait([1,event, "set auto forward sucess: "+str(new_forward_group)])
								else:
									msg_queue_H.put_nowait([1,event, str(new_forward_group)+"already added"])
							except Exception as e:
								msg_queue_H.put_nowait([1,event, "set auto forward fail: "+str(e)])
								print('add auto forward fail: ', str(e))
							finally:
								afd_list_lock.release()
						elif "afd remove=" in command:
							
							await remove_afd(int(command.split("=",1)[1]))
						elif "afd config=" in command:
							command = command.split("=")[1]
							_,_,_,_,_,_,_ = command.split(",")
						
							if await check_AF_db(command.split(",")[0]):
								if command.split(",")[1] =="1":
									if_media = True
								else:
									if_media = False
								if command.split(",")[2] =="1":
									if_link = True
								else:
									if_link = False
								if command.split(",")[3] =="1":
									if_fkey = True
								else:
									if_fkey = False
								if command.split(",")[4] =="1":
									if_me = True
								else:
									if_me = False
								if command.split(",")[5] =="1":
									if_filter = True
								else:
									if_filter = False
								if command.split(",")[6] =="1":
									if_dedupe = True
								else:
									if_dedupe = False
									
								await write_AF_setting_db(command.split(",")[0],if_media,if_link,if_fkey,if_me,if_filter,if_dedupe,me_id)
								
								print(command.split(",")[0]+" set to "+ str([if_media,if_link,if_fkey,if_me,if_filter,if_dedupe]))
								msg_queue_H.put_nowait([0,event, command.split(",")[0]+" set to: \nmedia:"+str(if_media)+"\nlink:"+str(if_link)+"\nfkey:"+str(if_fkey)+"\nme:"+str(if_me)+"\nfilter:"+str(if_filter)+"\ndedupe:"+str(if_dedupe)])
							else:
								print(command.split(",")[0]+" not in db afd list")
								msg_queue_H.put_nowait([0,event, command.split(",")[0]+" not in db afd list"])
						elif command.startswith("af :\n"):
							forward_group_list = command.split("\n")
							forward_group_list.pop(0)
							for group in forward_group_list:
								group = group.split("->",1)[0]
								if await get_actual_peer(int(group)) not in auto_forward_list:
									auto_forward_list.append(await get_actual_peer(int(group)))
									auto_forward_list_B.append(int(-1))
									msg_queue_H.put_nowait([0,event, "set auto forward sucess: "+group])
								else:
									msg_queue_H.put_nowait([0,event, group+" already in afd list"])
						elif command == "save":
							await save()
							msg_queue_H.put_nowait([1,event, "config saved"])	
						elif command =="load":
							try:
								await load()
								await get_status(event)
							except Exception as e:
								print('load(cmd):',str(e))
						elif command =="yes":
							
							if event.is_reply:
							
								await API_action_lock.acquire()
								try:
									reply_message = await event.get_reply_message()
								except Exception as e:
									raise ValueError(str(e))
								finally:
									await asyncio.sleep(actionlock_release_interval)
									API_action_lock.release()
									
								if "Add" in reply_message.message and "->(" in reply_message.message:
									new_afd = reply_message.message.split("->(")[0].replace("Add ","")
									if "PeerChannel" in new_afd:
										new_afd = new_afd.replace(")","").replace("PeerChannel(channel_id=","")
									elif "PeerChat" in new_afd:
										new_afd = new_afd.replace(")","").replace("PeerChat(chat_id=","")
									elif "PeerUser" in new_afd:
										new_afd = new_afd.replace(")","").replace("PeerUser(user_id=","")
										
									new_afd = int(new_afd)
									await afd_event_lock.acquire()
									try:
										if new_afd not in auto_forward_list and await check_AF_db(new_afd)==False:
											auto_forward_list.append(new_afd)
											auto_forward_list_B.append(int(-1))
											msg_queue_H.put_nowait([1,event, "add to afd list"])	
											await write_AF_db(new_afd,await get_display_name_from_id(new_afd),-1,me_id)
											print("ADD "+str(new_afd))
										else:
											msg_queue_H.put_nowait([1,event, "already in afd list"])	
									except Exception as e:
											print('Events handler error(auto forward): ', str(e))
									finally:
										afd_event_lock.release()
						elif command =="gt":
							if event.is_reply:
							
								await API_action_lock.acquire()
								try:
									reply_message = await event.get_reply_message()
								except Exception as e:
									raise ValueError(str(e))
								finally:
									await asyncio.sleep(actionlock_release_interval)
									API_action_lock.release()
									pass
								if "Add" in reply_message.message and "->(" in reply_message.message:
									GTID = reply_message.message.split("->(")[0].replace("Add ","")
									if "PeerChannel" in GTID:
										GTID = GTID.replace(")","").replace("PeerChannel(channel_id=","")
									elif "PeerChat" in GTID:
										GTID = GTID.replace(")","").replace("PeerChat(chat_id=","")
									elif "PeerUser" in GTID:
										GTID = GTID.replace(")","").replace("PeerUser(user_id=","")
										
									GTID = int(GTID)
									
									await GT_list_lock.acquire()
									try:
										if GTID not in GT_list and await check_GT_db(GTID)==False:
											GT_list.append(GTID)
											GT_list_B.append(0)
											loop = asyncio.get_event_loop()
											task = loop.create_task(get_all_handler(GTID))
											tasks.append(task)
											await write_GT_db(GTID,await get_display_name_from_id(GTID),0,me_id)
											msg_queue_H.put_nowait([1,event, "add to GT list"])
										else:
											msg_queue_H.put_nowait([1,event, "already in GT list"])
									except Exception as e:
											print('Events handler error(GT start): ', str(e))
									finally:
										GT_list_lock.release()
						elif "gt=" in command and "stop" not in command:
							actual_peer =  await get_actual_peer(int(command.split("=",1)[1]))							
							#GTID = int(command.split("=",1)[1])
							GTID = int(str(actual_peer).split("=")[1].replace(")",""))
							
							
							await GT_list_lock.acquire()
							try:
								if GTID not in GT_list and await check_GT_db(GTID)==False:
									GT_list.append(GTID)
									GT_list_B.append(0)
									await write_GT_db(GTID,await get_display_name_from_id(GTID),0,me_id)
									loop = asyncio.get_event_loop()
									task = loop.create_task(get_all_handler(GTID))
									tasks.append(task)
									msg_queue_H.put_nowait([1,event, str(GTID) + "add to GT list"])
								else:
									msg_queue_H.put_nowait([1,event, str(GTID) + "already in GT list"])
							except Exception as e:
									print('Events handler error(GT start): ', str(e))
							finally:
								GT_list_lock.release()
						elif "gt remove=" in command:
							GTID = int(command.split("=",1)[1])
							if GTID in GT_list:
								await remove_GT(GTID)
								msg_queue_H.put_nowait([1,event, str(GTID) + "remove from GT list"])
							else:
								msg_queue_H.put_nowait([1,event, str(GTID) + "not in GT list"])
						elif command =="start gt":
							# await GT_list_lock.acquire()
							loop = asyncio.get_event_loop()
							GT_pause = True
							try:
								for GTID in GT_list:
									task = loop.create_task(get_all_handler(GTID))
									tasks.append(task)
								msg_queue_H.put_nowait([0,event,"GT system restored"])
							except Exception as e:
									print('Events handler error(GT start): ', str(e))
							finally:
								# GT_list_lock.release()
								GT_pause = False
								pass
						elif command =="stop gt":
							for task in tasks:
								task.cancel()
							msg_queue_H.put_nowait([0,event,"All GT has stoped"])
							tasks=[]
						elif command =="reset gt":
							await GT_list_lock.acquire()
							try:
								i = 0
								for GT_state in GT_list_B:
									GT_list_B[i] = 0
									i+=1
								msg_queue_H.put_nowait([0,event,"gt has been reset"])
							except Exception as e:
									print('Events handler error(GT reset): ', str(e))
							finally:
								GT_list_lock.release()
						elif command =="reset afd":
							await afd_list_lock.acquire()
							try:
								i = 0
								for afd_state in auto_forward_list_B:
									auto_forward_list_B[i] = 0
									i+=1
								msg_queue_H.put_nowait([0,event,"afd has been reset"])
							except Exception as e:
									print('Events handler error(afd reset): ', str(e))
							finally:
								afd_list_lock.release()
						elif command =="clear gt":
							await GT_list_lock.acquire()
							try:
								GT_list =[]
								GT_list_B =[]
								msg_queue_H.put_nowait([0,event,"gt cleared"])
							except Exception as e:
									print('Events handler error(GT reset): ', str(e))
							finally:
								GT_list_lock.release()
						elif command =="clear afd":
							await afd_list_lock.acquire()
							try:
								auto_forward_list =[]
								auto_forward_list_B =[]
								msg_queue_H.put_nowait([0,event,"afd cleared"])
							except Exception as e:
									print('Events handler error(afd reset): ', str(e))
							finally:
								afd_list_lock.release()
						elif "add" in command and "->(" in command:
							pass
						elif command =="stop wk":
							await downloader_lock_norm.acquire()
							await downloader_lock_GT.acquire()
							print("WK stop")
							msg_queue_H.put_nowait([0,event, "WK stop"])
						elif command =="start wk":
							try:
								while 1==1:
									downloader_lock_norm.release()
							except:
								pass
							try:
								while 1==1:
									downloader_lock_GT.release()
							except:
								pass
							print("WK resume")
							msg_queue_H.put_nowait([0,event, "WK resume"])
						elif command =="stop pre":
							await downloader_lock_pre.acquire()
							print("pre stop")
							msg_queue_H.put_nowait([0,event, "pre stop"])
						elif command =="start pre":
							try:
								while 1==1:
									downloader_lock_pre.release()
							except:
								pass
							print("pre resume")
							msg_queue_H.put_nowait([0,event, "pre resume"])
						elif "set db=" in command:
							command = event.message.message.replace("set db=","")
							command = event.message.message.split("=",1)[1]
							await setDB(command.split(",")[0],command.split(",")[1],command.split(",")[2],command.split(",")[3])
						elif "rc chat=" in command:
							command = command.replace("rc chat=","")
							RC_chat_id = int(command)
							RC_entity = await client.get_entity(RC_chat_id)
						elif "rc=" in command:
							actual_peer =  await get_actual_peer(int(command.split("=",1)[1]))							
							#RCID = int(command.split("=",1)[1])
							RCID = int(str(actual_peer).split("=")[1].replace(")",""))
							
							if await check_db_conn() or RC_chat_id>0:
								await RC_list_lock.acquire()
								try:
									if RCID not in RC_list and await check_RC_db(RCID)==False:
										if await check_db_exist(RCID):
											pass
										else:
											await create_new_chat(RCID,await get_name_from_id(RCID))
										RC_list.append(RCID)
										RC_list_B.append(0)
										await write_RC_db(RCID,await get_display_name_from_id(RCID),0,me_id)
										msg_queue_H.put_nowait([1,event, str(RCID) + " add to RC list"])
									else:
										msg_queue_H.put_nowait([1,event, str(RCID) + " already in RC list"])
								except Exception as e:
										print('Events handler error(RC start): ', str(e))
								finally:
									RC_list_lock.release()
							else:
								msg_queue_H.put_nowait([1,event, "RC-regist:DB conn fail or RC_chat not set"])
						elif command =="rc":
							if event.is_reply:
							
								await API_action_lock.acquire()
								try:
									reply_message = await event.get_reply_message()
								except Exception as e:
									raise ValueError(str(e))
								finally:
									await asyncio.sleep(actionlock_release_interval)
									API_action_lock.release()
									pass
									
								if await check_db_conn() or RC_chat_id>0:
									if "Add" in reply_message.message and "->(" in reply_message.message:
										RCID = reply_message.message.split("->(")[0].replace("Add ","")
										if "PeerChannel" in RCID:
											RCID = RCID.replace(")","").replace("PeerChannel(channel_id=","")
										elif "PeerChat" in RCID:
											RCID = RCID.replace(")","").replace("PeerChat(chat_id=","")
										elif "PeerUser" in RCID:
											RCID = RCID.replace(")","").replace("PeerUser(user_id=","")
											
										RCID = int(RCID)
										
										await RC_list_lock.acquire()
										try:
											if RCID not in RC_list and await check_RC_db(RCID)==False:
												if await check_db_exist(RCID):
													pass
												else:
													await create_new_chat(RCID,reply_message.message.split("->(")[1].replace(")",""))
												RC_list.append(RCID)
												RC_list_B.append(0)
												await write_RC_db(RCID,await get_display_name_from_id(RCID),0,me_id)
												msg_queue_H.put_nowait([1,event, " add to RC list"])
											else:
												msg_queue_H.put_nowait([1,event, " already in RC list"])
										except Exception as e:
												print('Events handler error(RC start): ', str(e))
										finally:
											RC_list_lock.release()
								else:
									msg_queue_H.put_nowait([1,event, "RC-regist:DB conn fail or RC_chat not set"])
						elif "rc remove=" in command:
							RCID = int(command.split("=",1)[1])
							if RCID in RC_list:
								await remove_RC(RCID)
								msg_queue_H.put_nowait([1,event, str(RCID) + " remove from RC list"])
							else:
								msg_queue_H.put_nowait([1,event, str(RCID) + " not in RC list"])
						
						#--------------------------------------------
						elif command =="rc db list":
							pass
						elif "rc rebuild=" in command:
							pass
						
						#--------------------------------------------
						elif command =="msg transfer state":
							print("msg_H:"+str(msg_queue_H.qsize()))
							print("msg_L:"+str(msg_queue_L.qsize()))
						elif command =="event handler state":
							print("handleing: "+str(len(concurrent_event_handle_count)))
							print("allow max: "+str(concurrent_max_handle))
							print("handler_current:    "+str(handler_statistics))
							print("handler_statistics: "+str(handler_statistics_done))
						elif command =="bot state":
							#net speed
							S_rate = psutil.net_io_counters().bytes_recv
							await asyncio.sleep(1)
							E_rate = psutil.net_io_counters().bytes_recv
							net_rate = E_rate -S_rate
							net_rate = net_rate/1024./1024.
							
							print("msg_H:"+str(msg_queue_H.qsize()))
							print("msg_L:"+str(msg_queue_L.qsize()))
							print("handleing: "+str(len(concurrent_event_handle_count)))
							print("allow max: "+str(concurrent_max_handle))
							print("handler_current:    "+str(handler_statistics))
							print("handler_statistics: "+str(handler_statistics_done))
							print("\n------------------------------------------------------------\nWaiting : " + str(queue.qsize())+ "   Fail: "+str(error_count)+"\nSpeed:  "+ str(net_rate)[0:5]+"Mb/s \nMQ: "+str(missing_msg_queue.qsize())+"\nFile duplicate: "+str(file_duplicate_count)+"\nGT_queue: "+str(GT_queue.qsize()))
							print("\n------------------------------------------------------------\nCount:\nAF   -> "+str(len(auto_forward_list))+"\nGT   -> "+str(len(GT_list))+"\nEXT -> "+str(len(extra_AF_list))+"\nRC   -> "+str(len(RC_list)))
						
						elif command =="debug on":
							debug_mode=True
						elif command =="debug off":
							debug_mode=False
						elif command =="clear all rc":
							await RC_list_lock.acquire()
							try:
								RC_list=[]
								RC_list_B=[]
								msg_queue_H.put_nowait([1,event, "RC list clear"])
							except Exception as e:
									print('Events handler error(RC start): ', str(e))
							finally:
								RC_list_lock.release()
						elif command =="save to db":
							await save_to_DB()
							msg_queue_H.put_nowait([1,event, "save to db->done"])
						elif command =="clear all ignore":
							ignore_forward_list = []
							msg_queue_H.put_nowait([1,event, "Ignore list clear"])
							
						else:
							#print("MSG: Command -> " + str(command) + " is not Available")
							output = "MSG: Command -> " + str(command) + " is not Available"+"\n"+"Available commands: list, status, clean"
							if_send = True
						
						if if_send :
							#await log_reply(event, output)
							# for sub_msg in split_string(output, 4096):
								# await msg_queue_L.put([1,event, sub_msg])
							await msg_queue_L.put([1,event, output])

					if event.media:
						if hasattr(event.media, 'document') or hasattr(event.media,'photo'):
							filename=getFilename(event)
							await msg_queue_L.put([4,event, "{0} added to queue".format(filename)],)
						else:
							await msg_queue_L.put([0,event, "That is not downloadable. Try to send it as a file."])

				except Exception as e:
					if "'NoneType' object has no attribute 'media'" in str(e):
						pass
					else:
						print('Events handler error(bot chat): ', str(e))
				finally:
					#await asyncio.sleep(actionlock_release_interval*0.66)
					#event_handle_lock.release()
					pass
				
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[1]-=1
					handler_statistics_done[1]+=1
				except:
					print("handler_statistics error at del 1")
				finally:
					statistics_lock.release()
			
			
			elif event.message.message.lower() =="clr footprint":
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[2]+=1
				except:
					print("handler_statistics error at add 2")
				finally:
					statistics_lock.release()
					
				if (await event.get_sender()).id == me_id:
					await clr_footprint(event)
					
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[2]-=1
					handler_statistics_done[2]+=1
				except:
					print("handler_statistics error at del 2")
				finally:
					statistics_lock.release()
				
			elif TOID in auto_forward_list:
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[3]+=1
				except:
					print("handler_statistics error at add 3")
				finally:
					statistics_lock.release()
					
				afd_job_list=[]
					
				#1
				await afd_event_lock.acquire()
				try:
					batch_size =100
					old_msg_id = 0
					proc_msg_count = 0
					latest_monitor_msg_id = auto_forward_list_B[auto_forward_list.index(TOID)]
					old_msg_id = auto_forward_list_B[auto_forward_list.index(TOID)]
					current_id = event.message.id
					if_reload = False
					# if TOID==2133534883:
						# print("Proc1: "+str(event.message.id)+"....."+str(auto_forward_list_B[auto_forward_list.index(TOID)]))
					
					if latest_monitor_msg_id != -1 and int(current_id) != (latest_monitor_msg_id+1) and int(current_id) > latest_monitor_msg_id:
						if_reload = True
						#print("reload msg:"+str(latest_monitor_msg_id)+"....."+str(current_id))
						
						i=latest_monitor_msg_id+1
						while i<=int(current_id):
							if debug_mode:
								print("AFD stage1"+str(TOID_full)+"......."+str(i))
							
							msg_group = []
							if_skip = False
							actual_batch_size = 0
							
							if i+batch_size>=int(current_id):
								actual_batch_size = int(current_id)-i+1
								assert actual_batch_size<=99
							else:
								actual_batch_size = batch_size
								
							assert (i+actual_batch_size-1)<=int(current_id)
							assert actual_batch_size<=100
								
							await API_action_lock.acquire()
							try:
								# if TOID==2133534883:
									# print("Proc1-1: "+str(actual_batch_size+2)+"....."+str(i)+"....."+str(current_id))
								msg_group = await client.get_messages(TOID,limit=actual_batch_size+1, min_id=i,max_id=int(current_id),reverse=True)
								# if TOID==2133534883:
									# print("Proc1-1.1: "+str(len(msg_group)))
							except Exception as e:
								if_skip = True
								print(str(e))
								if "Invalid channel object. Make sure to pass the right types, for instance making sure that the request is designed for channels or otherwise look for a different one more suited" in str(e):
									pass
								else:
									raise ValueError(str(e))
							finally:
								await asyncio.sleep(actionlock_release_interval)
								API_action_lock.release()
								
								
							if if_skip == False:
								for event_message in msg_group:
									afd_job_list.append(event_message)
									# if TOID==2133534883:
										# print("Proc1-2: "+str(event.message.id))
							
								if len(msg_group)>0:
									if msg_group[len(msg_group)-1].id>=i+batch_size:
										i = msg_group[len(msg_group)-1].id-batch_size+1
							
							proc_msg_count+=len(msg_group)
							
							i+=batch_size
							
					latest_monitor_msg_id = int(current_id)
					if latest_monitor_msg_id>auto_forward_list_B[auto_forward_list.index(TOID)]:
						auto_forward_list_B[auto_forward_list.index(TOID)] = latest_monitor_msg_id
						
					
				except Exception as e:
					if "is not in list" in str(e):
						pass
					elif "'event_message' referenced before assignment" in str(e):
						pass
					elif "The channel specified is private and you lack permission to access it. Another reason may be that you were banned from it"  in str(e):
						status_refresh_req_flag = True
					else:
						print('Events handler error(auto forward-1): ', str(e))
						auto_forward_list_B[auto_forward_list.index(TOID)] = old_msg_id+proc_msg_count
				finally:
					afd_event_lock.release()
				#2	
				try:
					proc_msg_count = 0
					for afd_job in afd_job_list:
						await afd_handler_lock.acquire()
						try:
							# if TOID==2133534883:
								# print("Proc2: "+str(event.message.id)+"....."+str(auto_forward_list_B[auto_forward_list.index(TOID)]))
							await monitor_event_handler([],afd_job,TOID)
							await asyncio.sleep(actionlock_release_interval)
							proc_msg_count+=1
						except Exception as e:
							if "is not in list" in str(e):
								pass
							elif "The channel specified is private and you lack permission to access it. Another reason may be that you were banned from it"  in str(e):
								status_refresh_req_flag = True
							else:
								raise ValueError(str(e))
						finally:
							await asyncio.sleep(actionlock_release_interval)
							afd_handler_lock.release()
				except Exception as e:
					if "is not in list" in str(e):
						pass
					else:
						print('Events handler error(auto forward-2): ', str(e))
						await afd_event_lock.acquire()
						try:
							if auto_forward_list_B[auto_forward_list.index(TOID)]>old_msg_id+proc_msg_count:
								auto_forward_list_B[auto_forward_list.index(TOID)] = old_msg_id+proc_msg_count
						except Exception as e:
							pass
						finally:
							afd_event_lock.release()
							
				#3			
				try:
					if_proc = False
					
					await afd_event_lock.acquire()
					try:
						if int(current_id) < auto_forward_list_B[auto_forward_list.index(TOID)]:
							pass
						else:
							if_proc = True
							auto_forward_list_B[auto_forward_list.index(TOID)] = int(current_id)
					except:
						pass
					finally:
						afd_event_lock.release()
						
					if if_proc:
						# if TOID==2133534883:
							# print("Proc3: "+str(event.message.id)+"....."+str(auto_forward_list_B[auto_forward_list.index(TOID)]))
						await monitor_event_handler(event,event.message,TOID)
				except Exception as e:
					if "is not in list" in str(e):
						pass
					elif "'event_message' referenced before assignment" in str(e):
						pass
					elif "The channel specified is private and you lack permission to access it. Another reason may be that you were banned from it"  in str(e):
						status_refresh_req_flag = True
					elif "local variable 'current_id' referenced" in str(e):
						status_refresh_req_flag = True
					else:
						print('Events handler error(auto forward-3): ', str(e))
						await afd_event_lock.acquire()
						try:
							if auto_forward_list_B[auto_forward_list.index(TOID)]>old_msg_id+proc_msg_count:
								auto_forward_list_B[auto_forward_list.index(TOID)] = old_msg_id+proc_msg_count
						except:
							pass
						finally:
							afd_event_lock.release()
				finally:
					pass
				
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[3]-=1
					handler_statistics_done[3]+=1
				except:
					print("handler_statistics error at del 3")
				finally:
					statistics_lock.release()
					
			elif TOID_full in ignore_forward_list or (TOID in GT_list) or (TOID in RC_list):
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[4]+=1
				except:
					print("handler_statistics error at add 4")
				finally:
					statistics_lock.release()
				
				#pass
				
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[4]-=1
					handler_statistics_done[4]+=1
				except:
					print("handler_statistics error at del 4")
				finally:
					statistics_lock.release()
			else:
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[5]+=1
				except:
					print("handler_statistics error at add 5")
				finally:
					statistics_lock.release()
					
				try:
					if int(event.message.id)<=0:
						raise ValueError("event.message.id <=0")
					if (await event.get_sender()).id == me_id and (not event.media) and event.message:
						if event.message.message.lower() =="bot monitor":
							await afd_list_lock.acquire()
							try:
								auto_forward_list.append(TOID)
								auto_forward_list_B.append(int(event.message.id))
								await write_AF_db(TOID,await get_display_name_from_id(TOID),int(event.message.id),me_id)
								msg_queue_H.put_nowait([0,event, "add to afd list"])
								print("start monitor :" + str(event.to_id))
							except Exception as e:
								print('Events handler error: ', str(e))
							finally:
								afd_list_lock.release()
							
							await write_AF_db(str(event.to_id).split("=")[1].replace(")",""),"",me_id)
						elif event.message.message.lower() =="bot stop monitor":
								try:
									msg_queue_H.put_nowait([0,event, "was not set to monitor"])
								except Exception as e:
									print('Events handler error: ', str(e))
						else:
							pass
					else:
					
						disp_name = ""
						try:
							sender_id = int(str(event.to_id).split("=",1)[1].replace(")",""))
							
							if await check_id_name_db(str(sender_id)):
								disp_name = (await get_id_name_db(str(sender_id)))[0]
							else:	
								disp_name = str(await get_display_name_from_id(int(str(sender_id))))
								if disp_name is None:
									disp_name = "DeletedUser"
									await write_id_name_db(str(sender_id),"DeletedUser")
								else:
									await write_id_name_db(str(sender_id),disp_name)
						except Exception as e:
							print('Events handler error(oth event auto ask-1): ', str(e))
								
						await afd_event_lock.acquire()
						try:
							if event.to_id in ignore_forward_list or await peer_to_id(event.to_id) in auto_forward_list or await peer_to_id(event.to_id) in GT_list or await peer_to_id(event.to_id) in RC_list:
								pass
							else:
								robot_chat_entity = await client.get_entity(robot_chat)
								try:
									sender_id = event.to_id.channel_id
									# disp_name = str((await client.get_entity(PeerChannel(channel_id=event.to_id.channel_id))).title)
									msg_queue_H.put_nowait([6,robot_chat_entity, "Add "+ str(event.to_id)+"->("+disp_name+")?"])
								except Exception as e:
									try:
										sender_id = event.to_id.chat_id
										#disp_name = str((await client.get_entity(PeerChat(event.to_id.chat_id))).title)
										msg_queue_H.put_nowait([6,robot_chat_entity, "Add "+ str(event.to_id)+"->("+disp_name+")?"])
									except Exception as e:
										try:
											sender_id = event.to_id.user_id
											#disp_name = str((await client.get_entity(PeerUser(event.to_id.user_id))).username)
											if event.to_id != me_id_full:
												msg_queue_H.put_nowait([6,robot_chat_entity, "Add "+ str(event.to_id)+"->("+disp_name+")?"])
											
											
											
											if await get_actual_peer(event.sender_id) in ignore_forward_list or event.sender_id in auto_forward_list or event.sender_id in GT_list or event.sender_id in RC_list:
												pass
											else:
												sender_id = int(event.sender_id)
												if await check_id_name_db(str(sender_id)):
													disp_name = (await get_id_name_db(str(sender_id)))[0]
												else:	
													disp_name = str(await get_display_name_from_id(int(str(sender_id))))
													if disp_name is None:
														disp_name = "DeletedUser"
														await write_id_name_db(str(sender_id),"DeletedUser")
													else:
														await write_id_name_db(str(sender_id),disp_name)
														
												msg_queue_H.put_nowait([6,robot_chat_entity, "Add "+ str(await get_actual_peer(event.sender_id))+"->("+disp_name+")?"])
												ignore_forward_list.append(await get_actual_peer(event.sender_id))
										except Exception as e:
											print('Events handler error(oth event auto ask-2): ', str(e))
											
								if event.to_id != me_id_full:
									ignore_forward_list.append(event.to_id)
						except Exception as e:
							pass
						finally:
							afd_event_lock.release()
				except Exception as e:
					if "'NoneType' object has no attribute 'media'" in str(e):
						pass
					elif "'NoneType' object has no attribute 'id'" in str(e):
						pass
					else:
						print('Events handler error(oth event): ', str(e))
						
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[5]-=1
					handler_statistics_done[5]+=1
				except:
					print("handler_statistics error at del 5")
				finally:
					statistics_lock.release()
					
		except Exception as e:
			level0_error=True
			if "int() argument must be a string, a bytes-like object or a real number, not 'PeerChannel'" in str(e):
				pass
			else:
				print('event handle -level 0.b',str(e))
				
		try:
			try:
				RCID = int(TOID)
			except Exception as e:
				if "local variable 'TOID' referenced before assignment" in str(e):
					pass
				else:
					raise ValueError(str(e))
					
			if level0_error:
				pass
			elif RCID in RC_list:
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[6]+=1
				except:
					print("handler_statistics error at add 3")
				finally:
					statistics_lock.release()
					
				RC_job_list=[]
					
				#1
				await RC_list_lock.acquire()
				try:
					batch_size =100
					old_msg_id = 0
					proc_msg_count = 0
					latest_monitor_msg_id = RC_list_B[RC_list.index(RCID)]
					old_msg_id = RC_list_B[RC_list.index(RCID)]
					current_id = event.message.id
					if_reload = False
					RC_ID_list = []
					
					if latest_monitor_msg_id != -1 and int(current_id) != (latest_monitor_msg_id+1) and int(current_id) > latest_monitor_msg_id:
						if_reload = True
						
						i=latest_monitor_msg_id+1
						while i<=int(current_id):
							if debug_mode:
								print("RC stage1"+str(RCID)+"......."+str(i))
							
							msg_group = []
							if_skip = False
							actual_batch_size = 0
							
							if i+batch_size>=int(current_id):
								actual_batch_size = int(current_id) - i+1
								assert actual_batch_size<=99
							else:
								actual_batch_size = batch_size
								
							assert (i+actual_batch_size-1)<=int(current_id)
							assert actual_batch_size<=100
								
							await API_action_lock.acquire()
							try:
								msg_group = await client.get_messages(RCID,limit=actual_batch_size+1, min_id=i-1,max_id=int(current_id),reverse=True)
							except Exception as e:
								if_skip = True
								if "Invalid channel object. Make sure to pass the right types, for instance making sure that the request is designed for channels or otherwise look for a different one more suited" in str(e):
									pass
								else:
									raise ValueError(str(e))
							finally:
								await asyncio.sleep(actionlock_release_interval)
								API_action_lock.release()
								
								
							if if_skip == False:
								for event_message in msg_group:
									RC_job_list.append(event_message)
								
								if len(msg_group)>0:
									if msg_group[len(msg_group)-1].id>=i+batch_size:
										i = msg_group[len(msg_group)-1].id-batch_size+1
							
							proc_msg_count+=len(msg_group)
							
							i+=batch_size
							
					latest_monitor_msg_id = int(current_id)
					if latest_monitor_msg_id>RC_list_B[RC_list.index(RCID)]:
						RC_list_B[RC_list.index(RCID)] = latest_monitor_msg_id
						
					
				except Exception as e:
					if "is not in list" in str(e):
						pass
					elif "'event_message' referenced before assignment" in str(e):
						pass
					elif "The channel specified is private and you lack permission to access it. Another reason may be that you were banned from it"  in str(e):
						status_refresh_req_flag = True
					else:
						print('Events handler error(RC-1): ', str(e))
						RC_list_B[RC_list.index(RCID)] = old_msg_id+proc_msg_count
				finally:
					RC_list_lock.release()
				#2	
				try:
					proc_msg_count = 0
					for RC_job in RC_job_list:
						try:
							await RC_event_handler("new_message",RCID,RC_job)
							proc_msg_count+=1
						except Exception as e:
							if "is not in list" in str(e):
								pass
							elif "The channel specified is private and you lack permission to access it. Another reason may be that you were banned from it"  in str(e):
								status_refresh_req_flag = True
							else:
								raise ValueError(str(e))
						finally:
							pass
				except Exception as e:
					if "is not in list" in str(e):
						pass
					else:
						print('Events handler error(RC-2): ', str(e))
						await RC_list_lock.acquire()
						try:
							if RC_list_B[RC_list.index(RCID)]>old_msg_id+proc_msg_count:
								RC_list_B[RC_list.index(RCID)] = old_msg_id+proc_msg_count
						except Exception as e:
							pass
						finally:
							RC_list_lock.release()
							
				#3			
				try:
					if_proc = False
					
					await RC_list_lock.acquire()
					try:
						if int(current_id) < RC_list_B[RC_list.index(RCID)]and await check_record_exist(RCID,event.message.id):
							pass
						else:
							if_proc = True
							RC_list_B[RC_list.index(RCID)] = int(current_id)
					except Exception as e:
						pass
					finally:
						RC_list_lock.release()
						
					if if_proc:		
						await RC_event_handler("new_message",RCID,event.message)
				except Exception as e:
					if "is not in list" in str(e):
						pass
					elif "'event_message' referenced before assignment" in str(e):
						pass
					elif "The channel specified is private and you lack permission to access it. Another reason may be that you were banned from it"  in str(e):
						status_refresh_req_flag = True
					else:
						print('Events handler error(RC-3): ', str(e))
						await RC_list_lock.acquire()
						try:
							if RC_list_B[RC_list.index(RCID)]>old_msg_id+proc_msg_count:
								RC_list_B[RC_list.index(RCID)] = old_msg_id+proc_msg_count
						except:
							pass
						finally:
							RC_list_lock.release()
				finally:
					pass
				
				#handler statistics
				await statistics_lock.acquire()
				try:
					handler_statistics[6]-=1
					handler_statistics_done[6]+=1
				except:
					print("handler_statistics error at del 3")
				finally:
					statistics_lock.release()
			else:
				pass
		except Exception as e:
			level0_error=True
			if "int() argument must be a string, a bytes-like object or a real number, not 'PeerChannel'" in str(e):
				pass
			else:
				print('event handle -level 0.c',str(e))
		
		await event_handle_lock.acquire()
		try:
			#concurrent_event_handle_count.append(str(event.to_id)+"->"+str(event.message.id))
			await asyncio.sleep(actionlock_release_interval*0.8)
			concurrent_event_handle_count.pop(0)
			concurrent_max_handle = max(concurrent_max_handle-1,5)
		except:
			pass
		finally:
			event_handle_lock.release()
			
		#handler statistics
		await statistics_lock.acquire()
		try:
			handler_statistics[0]-=1
			handler_statistics_done[0]+=1
		except:
			print("handler_statistics error at del 0")
		finally:
			statistics_lock.release()

	async def worker():
		global error_count
		global status_update_time
		global file_duplicate_count
		
		
		while True:
		
			db_file_id = ''
			
			while client.is_connected() == False:
				print("waiting for reconnect")
				await asyncio.sleep(60)
			
			#await initail_lock.acquire()
			#initail_lock.release()
			await API_action_lock.acquire()
			API_action_lock.release()
			await downloader_lock_norm.acquire()
			downloader_lock_norm.release()
			
			
			p_ready =True
			new_event = []
			
			if p_ready:
				try:
					element = await queue.get()
					event=element[0]
					message=element[1]
					
					
					#new_event = event
					await API_action_lock.acquire()
					try:
						new_event = await client.get_messages(robot_chat_id, ids=event.message.id)
					except Exception as e:
						try:
							new_event = await client.get_messages(robot_chat_id, ids=event.id)
						except Exception as e2:
							raise ValueError(str(e2)+"....."+str(e))
					finally:
						await asyncio.sleep(actionlock_release_interval)
						API_action_lock.release()
						
					if await check_fileid_db(get_file_id(new_event)[0]):
						await msg_queue_L.put([1,message, "duplicate file id(skip)"])
						queue.task_done()
						await msg_queue_L.put([2,robot_chat_id, new_event.id])
						await msg_queue_L.put([2,robot_chat_id, message.id])
						continue
					
					
					filename=getFilename2(new_event)
					if filename.startswith("."):
						filename = str(time.time())+filename
					# if len(filename)>20:
						# filename =str(event.media.document.id) + os.path.splitext(getFilename(event))[1]
						
					fileName, fileExtension = os.path.splitext(filename)
					tempfilename=fileName+"-"+getRandomId(8)+fileExtension
					while path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(downloadFolder,tempfilename)):
						tempfilename=fileName+"-"+getRandomId(8)+fileExtension
						
					if path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(downloadFolder,filename)):
						if duplicates == "rename":
							filename=tempfilename
							
				except Exception as e:
					p_ready =False
					try: 
						# await remove_fileid_db(db_file_id)
						#await log_reply(message, "Error: {}".format(str(e))) # If it failed, inform the user about it.
						await msg_queue_L.put([1,message, "Error: {}".format(str(e))])
					except: pass
					print('Queue worker error: ', str(e))
			if p_ready:
				retry_flag = True
				retry_count = 0
				while retry_flag == True:			
					try:
						retry_flag = False
		 
						if hasattr(new_event.media, 'photo'):
							size = 0
						else: 
							size=new_event.media.document.size

						await msg_queue_L.put([1,message, "Downloading file {0} ({1} bytes)".format(filename,size)])

						download_callback = lambda received, total: set_progress(filename, message, received, total)
						
						await client.download_media(new_event.media, "{0}/{1}.{2}".format(tempFolder,filename,TELEGRAM_DAEMON_TEMP_SUFFIX), progress_callback = download_callback)
						
						
						await set_progress(filename, message, 100, 100)
						move("{0}/{1}.{2}".format(tempFolder,filename,TELEGRAM_DAEMON_TEMP_SUFFIX), "{0}/{1}".format(downloadFolder,filename))
						
						#check hash(duplicate check)
						await msg_queue_L.put([1,message, "{0} duplicate check".format(filename)])
						
						try:
							md5 = ""
							sha = ""
							if os.path.exists("{0}/{1}".format(downloadFolder,filename)):
								md5 = calculate_md5("{0}/{1}".format(downloadFolder,filename))
								sha = calculate_sha256("{0}/{1}".format(downloadFolder,filename))
							else:
								print("{0}/{1}".format(downloadFolder,filename)+"not exist!!!")
								md5 = ""
								sha = ""
						except Exception as e:
							md5 = ""
							sha = ""
							print('Queue worker error(hash): ', str(e))
							
						await hasher_lock.acquire()
						try:
							#print("MD5:" + md5)
							if os.path.exists("{0}/{1}".format(downloadFolder,filename)):
								if len(md5)>0 and len(sha)>0:
									if await check_hash_db(md5,sha):
										raise ValueError("md5 duplicate")
									else:
										await write_to_hash_db(md5,sha)
										
							#await log_reply(message, "{0} ready".format(filename))
							await msg_queue_L.put([1,message, "{0} ready".format(filename)])
						except Exception as e:
							if "md5 duplicate" in str(e) or "sha duplicate" in str(e):
								os.remove("{0}/{1}".format(downloadFolder,filename))
								await msg_queue_L.put([1,message, "{0} -> duplicate found(remove)".format(filename)])
								file_duplicate_count+=1
							else:
								print('Queue worker error(hash): ', str(e))
						finally:
							hasher_lock.release()
							
						if await check_fileid_db(get_file_id(new_event)[0]):
							pass
						else:
							db_file_id = get_file_id(new_event)[0]
							await write_fileid_db(get_file_id(new_event)[0])	
						
					
						queue.task_done()
						#delete message
						#await client.delete_messages(robot_chat_id, event.message.id)
						await msg_queue_L.put([2,robot_chat_id, new_event.id])
						#await client.delete_messages(robot_chat_id, message.id)
						await msg_queue_L.put([2,robot_chat_id, message.id])
						if time.time() - status_update_time >=600:# or len(in_progress) == 0:
							# await msg_queue_L.put([0,event, "status"])
							await msg_queue_L.put([6,robot_chat_id, "status"])
							status_update_time = time.time()
						else:
							pass
						
						
						
					except Exception as e:
						#remove frome status
						try:
							in_progress.pop(filename)
							await msg_queue_L.put([1,message, "Error: {}".format(str(e)+"\n Retrying......")])
						except:pass
						
						if "File name too long" in str(e):
							filename=str(new_event.media.document.id) + os.path.splitext(getFilename2(new_event))[1]
							fileName, fileExtension = os.path.splitext(filename)
							tempfilename=fileName+"-"+getRandomId(8)+fileExtension
							while path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(downloadFolder,tempfilename)):
								tempfilename=fileName+"-"+getRandomId(8)+fileExtension
								
							if path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(downloadFolder,filename)):
								if duplicates == "rename":
									filename=tempfilename
									
							retry_flag = True
						elif "No such file or directory:" in str(e) and retry_count<=MSG_trans_retry_limit:
							retry_flag = True
							retry_count+=1
						elif "Timeout while fetching data (caused by GetFileRequest)" in str(e) and retry_count<=MSG_trans_retry_limit:
							await asyncio.sleep(MSG_trans_retry_delay*retry_count)
							retry_flag = True
							retry_count+=1
						elif "The file reference has expired" in str(e) and retry_count<=MSG_trans_retry_limit:
							try:
								await API_action_lock.acquire()
								try:
									new_event = await client.get_messages(robot_chat_id, ids=new_event.id)
								except Exception as e:
									raise ValueError(str(e))
								finally:
									await asyncio.sleep(actionlock_release_interval)
									API_action_lock.release()
								
								retry_flag = True
								retry_count+=1
								
								await asyncio.sleep(MSG_trans_retry_delay)
							except Exception as e2:
								try:
									await msg_queue_L.put([1,message, "Error: {}".format(str(e)+"\n"+str(e2)+"\nDowload canceled or media not exist")])
								except: pass
								print('Queue worker error: ', str(e))
								error_count +=1
						 
						elif "'NoneType' object has no attribute 'media'" in str(e):
							try:
								await msg_queue_L.put([2,robot_chat_id, message.id])
							except: pass
						elif "A wait of" in str(e) and "seconds is required" in str(e):
							print('message transfer retry: ', str(e))
							await API_action_lock.acquire()
							try:
								await asyncio.sleep(int(str(e).split(" ")[3]))
							except Exception as e:
								print('Events handler error(GT handle mid1): ', str(e))
							finally:
								await asyncio.sleep(actionlock_release_interval)
								API_action_lock.release()
							retry_flag = True
						elif "Cannot send requests while disconnected" in str(e):
							await asyncio.sleep(120)
							retry_flag = True
							retry_count+=1
							
						else:
							# await remove_fileid_db(db_file_id)
							try: 
								await msg_queue_L.put([1,message, "Error: {}".format(str(e))])
							except: pass
							print('Queue worker error: ', str(e))
							error_count +=1
			
	async def GT_worker():
		global error_count
		global status_update_time
		global file_duplicate_count
		
		s_time =time.time()
		
		while True:
			db_file_id = ''
			
			while client.is_connected() == False:
				print("waiting for reconnect")
				await asyncio.sleep(60)
			#await initail_lock.acquire()
			#initail_lock.release()
			await API_action_lock.acquire()
			API_action_lock.release()
			await downloader_lock_GT.acquire()
			downloader_lock_GT.release()
			
			while time.time() - s_time < 0.9:
				await asyncio.sleep(0.4)
			p_ready =True
			new_event = []
			
			if p_ready:
				try:
					#element = await queue.get()
					element = await GT_queue.get() #[GTID,GT_B+1,save_directory]
					#event=element[0]
					
					await API_action_lock.acquire()
					try:
						event = await client.get_messages(element[0], ids=element[1])
					except:
						raise ValueError(str(e))
					finally:
						await asyncio.sleep(actionlock_release_interval)
						API_action_lock.release()	
					# message=element[1]
					new_event = event
					
					if await check_fileid_db(get_file_id(new_event)[0]):
						GT_queue.task_done()
						continue
					
					
					filename=getFilename2(event)
					if filename.startswith("."):
						filename = str(time.time())+filename
					# if len(filename)>20:
						# filename =str(event.media.document.id) + os.path.splitext(getFilename(event))[1]
						
					fileName, fileExtension = os.path.splitext(filename)
					tempfilename=fileName+"-"+getRandomId(8)+fileExtension
					while path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(element[2],tempfilename)):
						tempfilename=fileName+"-"+getRandomId(8)+fileExtension
						
					if path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(element[2],filename)):
						if duplicates == "rename":
							filename=tempfilename
							
				except Exception as e:
					p_ready =False
					# await remove_fileid_db(db_file_id)
					if "disconnected" in str(e):
						await GT_queue.put(element)
					else:
						print('GT_Queue worker error(stage1): ', str(e))
					
			if p_ready:
				retry_flag = True
				retry_count = 0
				while retry_flag == True:			
					try:
						retry_flag = False
		 
						await client.download_media(new_event.media, "{0}/{1}.{2}".format(tempFolder,filename,TELEGRAM_DAEMON_TEMP_SUFFIX))
						#await client.download_media(str(event.media.document.id), "{0}/{1}.{2}".format(tempFolder,filename,TELEGRAM_DAEMON_TEMP_SUFFIX), progress_callback = download_callback)
						
						
						#set_progress(filename, message, 100, 100)
						move("{0}/{1}.{2}".format(tempFolder,filename,TELEGRAM_DAEMON_TEMP_SUFFIX), "{0}/{1}".format(element[2],filename))
						
						#check hash(duplicate check)
						#await msg_queue_L.put([1,message, "{0} duplicate check".format(filename)])
						
						try:
							md5 = ""
							sha = ""
							if os.path.exists("{0}/{1}".format(element[2],filename)):
								md5 = calculate_md5("{0}/{1}".format(element[2],filename))
								sha = calculate_sha256("{0}/{1}".format(element[2],filename))
							else:
								print("{0}/{1}".format(element[2],filename)+"not exist!!!")
								md5 = ""
								sha = ""
						except Exception as e:
							md5 = ""
							sha = ""
							print('Queue worker error(hash): ', str(e))
							
						await hasher_lock.acquire()
						try:
							#print("MD5:" + md5)
							if os.path.exists("{0}/{1}".format(element[2],filename)):
								if len(md5)>0 and len(sha)>0:
									if await check_hash_db(md5,sha):
										raise ValueError("md5 duplicate")
									else:
										await write_to_hash_db(md5,sha)
										
							#await log_reply(message, "{0} ready".format(filename))
							#await msg_queue_L.put([1,message, "{0} ready".format(filename)])
						except Exception as e:
							if "md5 duplicate" in str(e) or "sha duplicate" in str(e):
								os.remove("{0}/{1}".format(element[2],filename))
								#await msg_queue_L.put([1,message, "{0} -> duplicate found(remove)".format(filename)])
								file_duplicate_count+=1
							else:
								print('Queue worker error(hash): ', str(e))
						finally:
							hasher_lock.release()
						
						
						if await check_fileid_db(get_file_id(new_event)[0]):
							pass
						else:
							db_file_id = get_file_id(new_event)[0]
							await write_fileid_db(get_file_id(new_event)[0])
					
						GT_queue.task_done()
						
						
						
					except Exception as e:
						#remove frome status
						try:
							in_progress.pop(filename)
							#await msg_queue_L.put([1,message, "Error: {}".format(str(e)+"\n Retrying......")])
						except:pass
						
						if "File name too long" in str(e):
							filename=str(event.media.document.id) + os.path.splitext(getFilename2(event))[1]
							fileName, fileExtension = os.path.splitext(filename)
							tempfilename=fileName+"-"+getRandomId(8)+fileExtension
							while path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(element[2],tempfilename)):
								tempfilename=fileName+"-"+getRandomId(8)+fileExtension
								
							if path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(element[2],filename)):
								if duplicates == "rename":
									filename=tempfilename
									
							retry_flag = True
						elif "No such file or directory:" in str(e) and retry_count<=MSG_trans_retry_limit:
							retry_flag = True
							retry_count+=1
						elif "Timeout while fetching data (caused by GetFileRequest)" in str(e) and retry_count<=MSG_trans_retry_limit:
							await asyncio.sleep(MSG_trans_retry_delay*retry_count)
							retry_flag = True
							retry_count+=1
						elif "The file reference has expired" in str(e) and retry_count<=MSG_trans_retry_limit:
							try:
								
								new_event = await client.get_messages(element[0], ids=element[1])
								
								retry_flag = True
								retry_count+=1
								
								await asyncio.sleep(MSG_trans_retry_delay)
								# error_count +=1
							except Exception as e2:
								if "disconnected" in str(e):
									await GT_queue.put(element)
								else:
									print('GT_Queue worker error(stage2.1): ', str(e))
									error_count +=1
						elif "'NoneType' object has no attribute 'media'" in str(e):
							try:
								#await msg_queue_L.put([2,robot_chat_id, message.id])
								pass
							except: pass
						elif "[Errno 2] No such file or directory: " in str(e) and "/unknown" in str(e):
							pass
						elif "[Errno 2] No such file or directory: " in str(e) and retry_count<=MSG_trans_retry_limit:
							tempfilename=fileName+"-"+getRandomId(8)+fileExtension
							while path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(element[2],tempfilename)):
								tempfilename=fileName+"-"+getRandomId(8)+fileExtension
								
							if path.exists("{0}/{1}.{2}".format(tempFolder,tempfilename,TELEGRAM_DAEMON_TEMP_SUFFIX)) or path.exists("{0}/{1}".format(element[2],filename)):
								if duplicates == "rename":
									filename=tempfilename
							retry_count+=1
							retry_flag = True
						elif "readexactly size can not be less than zero" == str(e):
							error_count +=1
						# elif "'NoneType' object has no attribute 'document'" in str(e):
							# try:
								# #await msg_queue_L.put([2,robot_chat_id, message.id])
								# pass
							# except: pass
						elif "A wait of" in str(e) and "seconds is required" in str(e):
							print('message transfer retry: ', str(e))
							await API_action_lock.acquire()
							try:
								await asyncio.sleep(int(str(e).split(" ")[3]))
							except Exception as e:
								print('Events handler error(GT handle mid1): ', str(e))
							finally:
								await asyncio.sleep(actionlock_release_interval)
								API_action_lock.release()
							retry_flag = True	
						elif "Cannot send requests while disconnected" in str(e):
							await asyncio.sleep(120)
							retry_flag = True
							retry_count+=1
							
						else:
							# await remove_fileid_db(db_file_id)
							if "disconnected" in str(e):
								await GT_queue.put(element)
							else:
								print('GT_Queue worker error(stage2): ', str(e))
								error_count +=1
			
	async def msg_transfer_worker():
		global MSG_trans_retry_delay
		global MSG_trans_retry_limit
		global MSG_transfer_rate
		global status_refresh_req_flag
		global status_msg
		global debug_mode
		global RC_chat_last_id
		global file_KEY_transfer_lock
		
		while 1==1:
			
			retry_flag = True
			retry_count = 0
			fail_code = 0
			Q_select = 0
			msg_element = []
			
			#0
			try:
				if debug_mode:
					print("msg transfer -0")
					
				while client.is_connected() == False:
					print("waiting for reconnect")
					await asyncio.sleep(60)
			except:
				pass
			
			#1
			try:
				if debug_mode:
					print("msg transfer -1")
				while msg_queue_H.qsize()==0 and  msg_queue_L.qsize()==0:
					if debug_mode:
						print("msg transfer -1.1")
					await asyncio.sleep(0.3)
				if msg_queue_H.qsize()>0:
					msg_element = await msg_queue_H.get()
					Q_select=1
				elif msg_queue_L.qsize()>0:
					msg_element = await msg_queue_L.get()
					Q_select=3
				else:
					retry_flag = False
					await asyncio.sleep(0.3)
					raise ValueError("no message(job) to transfer")
			except Exception as e:
				try:
					if "no message(job) to transfer" in str(e):
						pass
					else:
						print("message transfer error-1: "+ str(e))
				except Exception as e:
					print('Events handler error(msg transfer1): ', str(e))
					
			#1.1
			try:
				if msg_element[0]==6:
					if if_File_KEY(msg_element[2]):
						if file_KEY_transfer_lock==0:
							file_KEY_transfer_lock =1
						else:
							await msg_queue_L.put(msg_element)
							await asyncio.sleep(MSG_transfer_rate)
							continue
			except Exception as e:
				print('Events handler error(msg transfer1.1): ', str(e))
			
			
			#2
			
			try:
				if debug_mode:
					print("msg transfer -2")
				msg_element_group = []
				if msg_element[0] == 0:
					for msg in split_string(msg_element[2], 4096):
						msg_element_group.append([0,msg_element[1],msg])
				elif msg_element[0] == 1:
					for msg in split_string(msg_element[2], 4096):
						msg_element_group.append([1,msg_element[1],msg])
				elif msg_element[0] == 2:
					msg_element_group.append(msg_element)
				elif msg_element[0] == 3:
					msg_element_group.append(msg_element)
				elif msg_element[0] == 4:
					msg_element_group.append(msg_element)
				elif msg_element[0] == 5:
					msg_element_group.append(msg_element)
				elif msg_element[0] == 6:
					for msg in split_string(msg_element[2], 4096):
						msg_element_group.append([6,msg_element[1],msg])
				elif msg_element[0] == 7:
					msg_element_group.append(msg_element)
				elif msg_element[0] == 8:
					msg_element_group.append(msg_element)
			except Exception as e:
				if msg_element[0] == 7:
					RC_chat_last_id = -1
				print('Events handler error(msg transfer2): ', str(e))
				
					
			#3		
			while retry_flag:
				if debug_mode:
					print("msg transfer -3")
					
				retry_flag = False
				
				while client.is_connected() == False:
					print("waiting for reconnect")
					await asyncio.sleep(60)
					
				try:
					if retry_count>0 and debug_mode:
						print("msg transfer retry../n reason: "+str(fail_code))
						pass
				except Exception as e:
					pass
				try:
					if msg_element_group[0][0] == 0:
						for sub_msg_element in msg_element_group:
							message = await send_reply(sub_msg_element[1],sub_msg_element[2])
					elif msg_element_group[0][0] == 1:
						sub_msg_count = 0
						if_status_msg=False
						if "status report:\n------------------------------------------------------------\n" in msg_element_group[0][2]:
							if_status_msg=True
						#print(len(msg_element_group))
						for sub_msg_element in msg_element_group:
							if sub_msg_count==0:
								await sub_msg_element[1].edit(sub_msg_element[2])
							else:
								message=await client.send_message(await client.get_entity(sub_msg_element[1].to_id),sub_msg_element[2])
								if if_status_msg:
									status_msg.append(message.id)
							sub_msg_count+=1
					elif msg_element_group[0][0] == 2:
						for sub_msg_element in msg_element_group:
							await client.delete_messages(sub_msg_element[1], sub_msg_element[2])
					elif  msg_element_group[0][0] == 3:
						for sub_msg_element in msg_element_group:
							await client.forward_messages(sub_msg_element[1], sub_msg_element[2], sub_msg_element[3])
					elif  msg_element_group[0][0] == 4:
						for sub_msg_element in msg_element_group:
							message= await send_reply(sub_msg_element[1],sub_msg_element[2])
							await queue.put([sub_msg_element[1], message])
					elif  msg_element_group[0][0] == 5:
						for sub_msg_element in msg_element_group:
							await client.forward_messages(sub_msg_element[1], sub_msg_element[2], sub_msg_element[3])
							await client.delete_messages(sub_msg_element[1],sub_msg_element[2])
					elif  msg_element_group[0][0] == 6:
						for sub_msg_element in msg_element_group:
							await client.send_message(sub_msg_element[1],sub_msg_element[2])
					elif  msg_element_group[0][0] == 7:
						for sub_msg_element in msg_element_group:
							await client.forward_messages(sub_msg_element[1], sub_msg_element[2], sub_msg_element[3])
						RC_chat_last_id = -2
					elif  msg_element_group[0][0] == 8:
						for sub_msg_element in msg_element_group:
							#print(sub_msg_element)
							
							original_msg = await client.get_messages( sub_msg_element[2], ids= sub_msg_element[1])
								
							
							# doc = InputDocument(file_id, access_hash, file_reference)
							try:
								await sub_msg_element[5].reply(original_msg)
								# await client.send_file(sub_msg_element[4], doc, reply_to=sub_msg_element[3])
							except Exception as e:
								print(str(e))
							
							
				except Exception as e:
					try:
						if "no message(job) to transfer" in str(e):
							fail_code=1
							pass
						elif "Content of the message was not modified (caused by EditMessageRequest)" in str(e):
							fail_code=2
							pass
						elif "A wait of" in str(e) and "seconds is required" in str(e):
							fail_code=3
							print('message transfer retry: ', str(e))
							await API_action_lock.acquire()
							try:
								await asyncio.sleep(int(str(e).split(" ")[3]))
							except Exception as e:
								print('Events handler error(msg transfer3-2): ', str(e))
							finally:
								await asyncio.sleep(actionlock_release_interval)
								API_action_lock.release()
							retry_flag = True
						elif "The specified message ID is invalid or you can't do that operation on such message" in str(e):
							fail_code=4
						elif "You can't forward messages from a protected chat" in str(e):
							fail_code=5
							#status_refresh_req_flag =True
						elif "The channel specified is private and you lack permission to access it" in str(e):
							fail_code=6
							status_refresh_req_flag =True
						elif "Invalid channel object. Make sure to pass the right types, for instance making sure that the request is designed for channels or otherwise look for a different one more suited" in str(e):
							fail_code=7
							status_refresh_req_flag =True
						elif "The provided media object is invalid or the current account may not be able to send it" in str(e):
							fail_code=8
						elif (msg_element[0] == 4 or msg_element[0] == 5) and retry_count<=MSG_trans_retry_limit:
							fail_code=9
							retry_flag = True
							print("message transfer error-3 code 9: "+str(msg_element[0])+": "+ str(e))
							await asyncio.sleep(MSG_trans_retry_delay)
						else:
							fail_code=10
							print("message transfer error-3: "+str(msg_element[0])+": "+ str(e))
							print(msg_element)
							
						if msg_element[0] == 7 and retry_flag == False:
							RC_chat_last_id = -1
					except Exception as e:
						print('Events handler error(msg transfer3): ', str(e))
						
				await asyncio.sleep(MSG_transfer_rate)
			#4
			try:
				if debug_mode:
					print("msg transfer -4")
					
				if Q_select==1:
					msg_queue_H.task_done()
				elif Q_select==3:
					msg_queue_L.task_done()
				else:
					pass
			except Exception as e:
				try:
					print("message transfer error-4: "+ str(e))
				except Exception as e:
					print('Events handler error(msg transfer4): ', str(e))
		
		print("msg WK fail!!!!")
		
	async def RC_media_worker_sub():
		global RC_chat_id
		global RC_chat_last_id
		
		while 1==1:
			try:
				if RC_chat_last_id == -2:
					await API_action_lock.acquire()
					try:
						latest_message = await client.get_messages(RC_chat_id, limit=1)
						RC_chat_last_id = latest_message[0].id
					except Exception as e:
						RC_chat_last_id = -1
						print('RC_media_worker_sub -1: ', str(e))
					finally:
						await asyncio.sleep(actionlock_release_interval)
						API_action_lock.release()
				else:
					await asyncio.sleep(0.1)
			except Exception as e:
				RC_chat_last_id = -1
				print('RC_media_worker_sub -2: ', str(e))
		
	async def msg_fill_worker():
		
		#await initail_lock.acquire()
		#initail_lock.release()
		while 1==1:
			while len(concurrent_event_handle_count) >10 or msg_queue_L.qsize()>10:
				await asyncio.sleep(10)
		
			try:
				missing_id = await missing_msg_queue.get()
				await API_action_lock.acquire()
				try:
					message = await client.get_messages(robot_chat_id, ids=missing_id)
				except Exception as e:
					print('msg fill worker-1: ', str(e))
				finally:
					await asyncio.sleep(actionlock_release_interval)
					API_action_lock.release()
					pass
				if message.media :
					#print("resend:" + str(missing_id))
					await msg_queue_L.put([3,robot_chat_id,missing_id,robot_chat_id])
					await msg_queue_L.put([2,robot_chat_id, missing_id])
				else:
					pass
			except Exception as e:
				if "'NoneType' object has no attribute 'media'" in str(e):
					pass
				elif "'NoneType' object has no attribute 'id'" in str(e):
					pass
				else:
					print("message resend error: ("+ str(missing_id) +")"+str(e) )
				
			await asyncio.sleep(2)
				
	async def clr_footprint(event):
		clr_count = 0
		async for message in client.iter_messages(event.to_id, from_user='me'):
			try:
				clr_count+=1
				await msg_queue_L.put([2,event.to_id, message.id])
			except Exception as e:
				pass
		
		print("clr count: "+str(clr_count))
			
	async def pre_forward():
		global concurrent_event_handle_count
		
		history_msg = []
		await asyncio.sleep(60)
		await initail_lock.acquire()
		initail_lock.release()
			
		print("start reading")
		async for message in client.iter_messages(robot_chat_id, reverse= True):
			history_msg.append(message.id)
			await asyncio.sleep(0.2)
		
		print("finish reading message count: "+ str(len(history_msg)))
		
		for msg_id in history_msg:
			await downloader_lock_norm.acquire()
			downloader_lock_norm.release()
			await downloader_lock_GT.acquire()
			downloader_lock_GT.release()
			await downloader_lock_pre.acquire()
			downloader_lock_pre.release()
			
			while len(concurrent_event_handle_count) >10 or msg_queue_L.qsize()>10:
				await asyncio.sleep(10)
			
			await API_action_lock.acquire()
			try:
				message = await client.get_messages(robot_chat_id, ids=msg_id)
			except Exception as e:
				print('pre forward-1: ', str(e))
			finally:
				await asyncio.sleep(actionlock_release_interval)
				API_action_lock.release()
				pass
			try:
				if message.media :
					# await msg_queue_L.put([5,robot_chat_id, msg_id, robot_chat_id])
					if hasattr(message.media, 'document') or hasattr(message.media,'photo'):
						filename=getFilename2(message)
						await msg_queue_L.put([4,message, "{0} added to queue".format(filename)],)
					
				else:
					await msg_queue_L.put([2,robot_chat_id, msg_id])
			except Exception as e:
					print('pre forward error-2: ', str(e))
			await asyncio.sleep(1)
			
		print("finish pre forward")
	
	async def get_actual_peer(ID):
		peer = PeerChannel(ID)
		await API_action_lock.acquire()
		try:
			name = str((await client.get_entity(PeerChannel(ID))).title)
			peer = PeerChannel(ID)
		except Exception as e:
			try:
				name = str((await client.get_entity(PeerChat(ID))).title)
				peer = PeerChat(ID)
			except Exception as e:
				try:
					name = str((await client.get_entity(PeerUser(ID))).username)
					peer = PeerUser(ID)
				except Exception as e:
					pass
		finally:
			await asyncio.sleep(actionlock_release_interval)
			API_action_lock.release()
		return peer
		
	async def get_actual_peer_from_peer(peer):
		ID = str(peer)
		ID = ID.split("=")[1]
		ID = ID.split(")")[0]
		ID = int(ID)
		await API_action_lock.acquire()
		try:
			name = str((await client.get_entity(PeerChannel(ID))).title)
			peer = PeerChannel(ID)
		except Exception as e:
			try:
				name = str((await client.get_entity(PeerChat(ID))).title)
				peer = PeerChat(ID)
			except Exception as e:
				try:
					name = str((await client.get_entity(PeerUser(ID))).username)
					peer = PeerUser(ID)
				except Exception as e:
					pass
		finally:
			await asyncio.sleep(actionlock_release_interval)
			API_action_lock.release()
		return peer
	
	async def peer_to_id(peer):
		ID = peer
		await API_action_lock.acquire()
		try:
			name = str((await client.get_entity(PeerChannel(channel_id=peer.channel_id))).title)
			ID = peer.channel_id
		except Exception as e:
			try:
				name = str((await client.get_entity(PeerChat(peer.chat_id))).title)
				ID = peer.chat_id
			except Exception as e:
				try:
					name = str((await client.get_entity(PeerUser(peer.user_id))).username)
					ID = peer.user_id
				except Exception as e:
					pass
		finally:
			await asyncio.sleep(actionlock_release_interval)
			API_action_lock.release()
		return int(ID)
	
	async def remove_afd(AFID):
		await afd_list_lock.acquire()
		try:
			auto_forward_list_B.pop(auto_forward_list.index(AFID))
			auto_forward_list.remove(AFID)
			msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), str(AFID)+" removed from afd list"])
			
			# ID = str(channel_id).split("=")[1].replace(")","").replace("=","")
			await remove_AF_db(AFID,me_id)
			
			print("stop monitor :" + str(AFID))
		except Exception as e:
			print('Events handler error(remove afd): ', str(e))
			try:
				if_remove =False
				for AFDID in auto_forward_list:
					if AFDID == AFID:
						auto_forward_list_B.pop(auto_forward_list.index(AFDID))
						auto_forward_list.remove(AFDID)
						msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), str(AFID)+" removed from afd list"])
						
						# ID = str(channel_id).split("=")[1].replace(")","").replace("=","")
						await remove_AF_db(AFID,me_id)
						
						print("stop monitor :" + str(AFID))
						if_remove =True
						break
				if if_remove ==False:
					msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), str(AFID)+" not in afd list"])
					print(str(AFID)+"not in afd list")
			except Exception as e:
				print('Events handler error(remove afd): ', str(e))
		finally:
			afd_list_lock.release()
			
	async def remove_GT(GTID):
		if GTID in GT_list:
			await GT_list_lock.acquire()
			try:
				GT_index = GT_list.index(GTID)
				GT_list.pop(GT_index)
				GT_list_B.pop(GT_index)
				await remove_GT_db(GTID,me_id)
			except Exception as e:
					print('Events handler error(GT stop): ', str(e))
			finally:
				GT_list_lock.release()
				
	async def remove_RC(RCID):
		if RCID in RC_list:
			await RC_list_lock.acquire()
			try:
				RC_index = RC_list.index(RCID)
				RC_list.pop(RC_index)
				RC_list_B.pop(RC_index)
				await remove_RC_db(RCID,me_id)
			except Exception as e:
					print('Events handler error(RC stop): ', str(e))
			finally:
				RC_list_lock.release()
	
	def if_File_KEY(msg):
		try:
			if_KEY = False
			
			if msg is not None:
				for submsg in msg.split("\n"):
					if ("fd_" in msg or "p_" in msg or "d_" in msg or "vi_" in msg or "pk_" in msg or "fds_" in msg) and ("https://" not in msg) and ("http://" not in msg) and len(msg) >15:
						if_KEY =  True
					
			return if_KEY
		except Exception as e:
			if "argument of type 'NoneType' is not iterable" in str(e):
				pass
			else:
				print('Events handler error(if_File_KEY): ', str(e))
	
	def if_URL(msg):
		try:
			msg = msg.lower()
			if ("https" in msg or "http" in msg or "t.me" in msg or ("+" in msg and len(msg)>10)):
				return True
			else:
				return False
		except Exception as e:
			if "'NoneType' object has no attribute 'lower'" in str(e):
				pass
			else:
				print('Events handler error(if_URL): ', str(e))
		
	async def File_Key_handler(msg,from_id,if_dedupe):
		global file_drive_entity
		
		msg = await apply_replace_rule(msg)
		
		try:
			
			if await check_afd_msg_history(msg) and if_dedupe:
				return 0
			
			#forward original msg
			await API_action_lock.acquire()
			try:
				await msg_queue_L.put([6,file_drive_entity,str(from_id)+"\nfull\n"+msg])
			finally:
				await asyncio.sleep(actionlock_release_interval)
				API_action_lock.release()
			
			#forward separated msg
			file_code_list = separate_file_code(msg)
			if len(file_code_list) >1:
				for code in file_code_list:
					
					if await check_afd_msg_history(code):
						continue
					else:
						await write_to_msg_history_db(code)
						
					await API_action_lock.acquire()
					try:
						await msg_queue_L.put([6,file_drive_entity,str(from_id)+"\npart\n"+code])
					finally:
						await asyncio.sleep(actionlock_release_interval)
						API_action_lock.release()
						
			await write_to_msg_history_db(msg)
		except Exception as e:
			print('Events handler error(File_Key_handler): ', str(e))
			
	async def monitor_event_handler(event,event_message,TOID):
		global message_record_list
		global me_id
		global ID_NAME
		
		sender_id = 0
		
		try:
			while client.is_connected() == False:
				print("waiting for reconnect")
				await asyncio.sleep(60)
				
			
			
			# if TOID==2133534883:
				# print(str(if_File_KEY(event_message.message))+"....."+event_message.message+"....."+str(event_message.id))
			
			if_media,if_link,if_fkey,if_me,if_filter,if_dedupe = await read_AF_setting_db(TOID,me_id)
			
			if if_me==False:
				if event_message.from_id is not None:
					try:
						sender_id = event_message.sender_id
					except Exception as e:
						print('monitor_event_handler-1: ',str(e))
						
						await API_action_lock.acquire()
						try:
							sender_id = (await event_message.get_sender()).id
						finally:
							await asyncio.sleep(actionlock_release_interval)
							API_action_lock.release()
				else:
						sender_id = TOID
						# await API_action_lock.acquire()
						# try:
							# print("B-2.1")
							# sender_id = (await event_message.get_sender()).id
							# print("B-2.2")
						# finally:
							# await asyncio.sleep(actionlock_release_interval)
							# API_action_lock.release()
				if sender_id ==None:
					sender_id = TOID
				
				if sender_id == me_id and event_message.message.lower() !="bot monitor" and event_message.message.lower() !="bot stop monitor":
					return 0
			
			
			if (not event_message.media) and event_message.message :
				command = event_message.message
				command = command.lower()
				output = "Unknown command"
				if len(str(sender_id)) != 0:
					if event_message.from_id is not None:
						try:
							sender_id = event_message.sender_id
						except Exception as e:
							print('monitor_event_handler-2: ',rstr(e))
							
							await API_action_lock.acquire()
							try:
								sender_id = (await event_message.get_sender()).id
							finally:
								await asyncio.sleep(actionlock_release_interval)
								API_action_lock.release()
					else:
						sender_id = TOID
						# await API_action_lock.acquire()
						# try:
							# print("B-2.1")
							# sender_id = (await event_message.get_sender()).id
							# print("B-2.2")
						# finally:
							# await asyncio.sleep(actionlock_release_interval)
							# API_action_lock.release()
					if sender_id ==None or sender_id ==0:
						sender_id = TOID
				
				await asyncio.sleep(actionlock_release_interval)
				
				
				if sender_id == me_id and event_message.message.lower() =="bot monitor":
					try:
						msg_queue_H.put_nowait([0,event, "already in afd list"])
					except Exception as e:
						print('Events handler error: ', str(e))
				elif sender_id == me_id and event_message.message.lower() =="bot stop monitor":
					await remove_afd(TOID)
				elif if_fkey and if_File_KEY(command):
					
					sender_name = ""
					if await check_id_name_db(str(sender_id)):
						sender_name = (await get_id_name_db(str(sender_id)))[0]
					else:	
						sender_name = str(await get_display_name_from_id(int(str(sender_id))))
						if sender_name is None:
							sender_name = "DeletedUser"
							await write_id_name_db(str(sender_id),"DeletedUser")
						else:
							await write_id_name_db(str(sender_id),sender_name)
					# if TOID==1940780881:
						# print("AAAAA")
					
					await File_Key_handler(event_message.message,str(sender_id)+"("+sender_name+")",if_dedupe)
					await asyncio.sleep(actionlock_release_interval)
					await EXT_AFD_handler_TXT(event_message.message,TOID)
					await asyncio.sleep(actionlock_release_interval)
				elif if_link and if_URL(command):
					if await check_afd_msg_history(command) and if_dedupe:
						pass
					else:
						await write_to_msg_history_db(command)
						await msg_queue_L.put([6,"me",event_message.message])
						await EXT_AFD_handler_TXT(event_message.message,TOID)
						await asyncio.sleep(actionlock_release_interval)
						# await msg_queue_L.put([3,"me",event_message.id,event_message.to_id])
				else:
					pass
				
			elif if_media and event_message.media and (not event_message.sticker) and (not event_message.poll) and (not event_message.audio) and (not event_message.voice):
				if if_filter and len(event_message.message)>40 and if_File_KEY(event_message.message)==False and await check_afd_msg_history(event_message.message):
					return 0
				elif await check_afd_msg_history(event_message.message)==False and len(event_message.message)>40:
					await write_to_msg_history_db(event_message.message)
					
				if if_filter and await check_fileid_db(get_file_id(event_message)[0]):
					return 0 
				else:
					pass
					# await write_fileid_db(get_file_id(event_message)[0])	
					
				await msg_queue_H.put([3,"me",event_message.id,await get_actual_peer(TOID)])
				await EXT_AFD_handler_FD_reply(event_message,event_message.id,TOID)
				await asyncio.sleep(actionlock_release_interval)
				
		except Exception as e:
			if "'NoneType' object has no attribute 'media'" in str(e):
				pass
			elif "'NoneType' object has no attribute 'id'" in str(e):
				pass
			elif "disconnected" in str(e):
				raise ValueError(str(e))
			elif "int() argument must be a string, a bytes-like object or a real number, not 'PeerChannel'" in str(e):
				pass
			else:
				print('Events handler error(auto forward handler): ', str(e))
		
	async def get_name_from_id(ID):
		name = ""
		await API_action_lock.acquire()
		try:
			name = str((await client.get_entity(PeerChannel(ID))).title)
		except Exception as e:
			if "The channel specified is private and you lack permission to access it" in str(e):
				name = "The channel specified is private and you lack permission to access it"
			else:
				try:
					name = str((await client.get_entity(PeerChat(ID))).title)
				except Exception as e:
					if "The channel specified is private and you lack permission to access it" in str(e):
						name = "The channel specified is private and you lack permission to access it"
					else:
						try:
							name = str((await client.get_entity(PeerUser(ID))).username)
						except Exception as e:
							if "The channel specified is private and you lack permission to access it" in str(e):
								name = "The channel specified is private and you lack permission to access it"
							else:
								name = str(ID)
		finally:
			await asyncio.sleep(actionlock_release_interval)
			API_action_lock.release()
		return name
	
	async def get_display_name_from_id(ID):
		name = ""
		#await API_action_lock.acquire()
		try:
			name = utils.get_display_name(await client.get_entity(await get_actual_peer(ID)))
		except Exception as e:
			if "The channel specified is private and you lack permission to access it" in str(e):
				name = "Deleted Account(bot)"
			elif "Could not find the input entity for" in str(e):
				name = "Unknow("+str(ID)+")"
			else:
				print('get_display_name',str(e))
		finally:
			#API_action_lock.release()
			await asyncio.sleep(actionlock_release_interval)
			pass
		return name
	
	def get_file_id(event):
		file_id = ""
		access_hash = ""
		file_reference = ""
		
		if event.document:
			document = event.document
			# Extract access_hash and file_reference
			file_id = document.id
			access_hash = document.access_hash
			file_reference = document.file_reference

		# Check if the message contains a photo
		elif event.photo:
			photo = event.photo
			# Extract access_hash and file_reference
			file_id = photo.id
			access_hash = photo.access_hash
			file_reference = photo.file_reference
		else:
			pass
			
		return file_id,access_hash,file_reference
	
	async def EXT_AFD_handler_FD_reply(event_msg,msg_id,from_channel):
		global extra_AF_list
		
		try:
			for i in range(0,len(extra_AF_list)):
				if str(extra_AF_list[i][0])  == str(int(from_channel)) :
					if event_msg.is_reply:
						
						target_msgid =-1
						target_event = []
					
						await API_action_lock.acquire()
						try:
							target_msg = (await event_msg.get_reply_message()).message
						except Exception as e:
							raise ValueError(str(e))
						finally:
							await asyncio.sleep(actionlock_release_interval)
							API_action_lock.release()
							
						###temp####
						if len(target_msg.split("\n"))>2:
							target_msg =target_msg.split("\n")[2]
						###########
							
						await reply_history_lock.acquire()
						try:
							async for message in client.iter_messages(int(extra_AF_list[i][1]), reverse= False,limit = 200):
								if target_msg in message.message and [int(extra_AF_list[i][1]),int(message.id)]not in reply_history:
									target_msgid = int(message.id)
									target_event = message
									reply_history.append([int(extra_AF_list[i][1]),int(message.id)])
									break
							
								await asyncio.sleep(0.2)
						except Exception as e:
							print('Events handler error(EXT AFD FD-1): ', str(e))
						finally:
							reply_history_lock.release()
							
						if target_msgid>0:
							await msg_queue_L.put([8,msg_id,from_channel,target_msgid,extra_AF_list[i][1],target_event])
						else:
							await msg_queue_L.put([3,await client.get_entity(int(extra_AF_list[i][1])),msg_id,await get_actual_peer(from_channel)])
						
					else:
						await msg_queue_L.put([3,await client.get_entity(int(extra_AF_list[i][1])),msg_id,await get_actual_peer(from_channel)])
		except Exception as e:
			print('Events handler error(EXT AFD FD-2): ', str(e))
	
	async def EXT_AFD_handler_FD(msg_id,from_channel):
		global extra_AF_list
		try:
			for i in range(0,len(extra_AF_list)):
				if str(extra_AF_list[i][0])  == str(int(from_channel)) :
					# print(str(await get_actual_peer(from_channel)))
					await msg_queue_L.put([3,await client.get_entity(int(extra_AF_list[i][1])),msg_id,await get_actual_peer(from_channel)])
		except Exception as e:
			print('Events handler error(EXT AFD FD): ', str(e))
				
	async def EXT_AFD_handler_TXT(msg,from_channel):
		global extra_AF_list
		try:
			for i in range(0,len(extra_AF_list)):
				if str(extra_AF_list[i][0]) == str(int(from_channel)):
					await msg_queue_L.put([6,await client.get_entity(int(extra_AF_list[i][1])),msg])
		except Exception as e:
			print('Events handler error(EXT AFD TXT): ', str(e))
	
	async def get_all_handler(GTID):
		global GT_list
		global GT_list_B
		global GT_pause
		global ID_NAME
		global status_refresh_req_flag
		
		batch_size = 50
		
		new_GT_B = 0
		GT_B = -1
		save_directory = "../collect/"+await get_name_from_id(GTID)
		
		while GT_pause ==True:
			await asyncio.sleep(15)
			pass
		
		if not os.path.exists(save_directory):
			os.makedirs(save_directory)
			
		while GTID in GT_list:
			
			while client.is_connected() == False:
				print("waiting for reconnect")
				await asyncio.sleep(60)
				
			await asyncio.sleep(60)
			# print("GT test A")
			await GT_list_lock.acquire()
			try:
				if GTID in GT_list:
					GT_index = GT_list.index(GTID)
					GT_B = GT_list_B[GT_index]
					new_GT_B = GT_B
				else:
					GT_B = -1
			except Exception as e:
				if "Telegram is having internal issues RpcCallFailError: Telegram is having internal issues, please try again later." in str(e):
					print(str(GTID)+" sleep for 60 second")
					await asyncio.sleep(60)
				else:
					print('Events handler error(GT handle stage1): ', str(e))
			finally:
				GT_list_lock.release()
				
			
			if GT_B>=0:
				i_temp = GT_B
				try:
					latest_message = await client.get_messages(GTID, limit=1)
					latest_message_id = latest_message[0].id
					if GT_B<latest_message_id:
						for i in range(GT_B,latest_message_id+1,batch_size):
							
							while client.is_connected() == False:
								print("waiting for reconnect")
								await asyncio.sleep(60)
								
							i_temp=i
							await asyncio.sleep(15)
							
							#msg = await client.get_messages(GTID, ids=i)
							msg_group = []
							
							await API_action_lock.acquire()
							try:
								msg_group = await client.get_messages(GTID,limit=batch_size, min_id=i,reverse=True)
							except Exception as e:
								print('Events handler error(GT handle mid1): ', str(e))
							finally:
								await asyncio.sleep(actionlock_release_interval)
								API_action_lock.release()
							j= 0
							for msg in msg_group:
								try:
									if if_File_KEY(msg.message):
										sender_name = ""
										if await check_id_name_db(str(GTID)):
											sender_name = (await get_id_name_db(str(GTID)))[0]
										else:	
											sender_name = str(await get_display_name_from_id(int(str(GTID))))
											if sender_name is None:
												sender_name = "DeletedUser"
												await write_id_name_db(str(GTID),"DeletedUser")
											else:
												await write_id_name_db(str(GTID),sender_name)
										await File_Key_handler(msg.message,"("+sender_name+")",True)
										await EXT_AFD_handler_TXT(msg.message,GTID)
								except Exception as e:
									pass
									print('Events handler error(GT handler-1): ', str(e))
								try:
									if if_URL(msg.message):
										if await check_afd_msg_history(msg.message):
											pass
										else:
											await write_to_msg_history_db(msg.message)
											await msg_queue_L.put([6,"me",msg.message])
											await EXT_AFD_handler_TXT(msg.message,GTID)
								except Exception as e:
									pass
									print('Events handler error(GT handler-2): ', str(e))
								try:
									if msg.media:
										if hasattr(msg.media, 'document') or hasattr(msg.media,'photo'):
											await GT_queue.put([GTID,msg.id,save_directory])
											await EXT_AFD_handler_FD(msg.id,GTID)
								except Exception as e:
									pass
									print('Events handler error(GT handler-3): ', str(e))
								j+=1
								new_GT_B = i+j
							if i+batch_size >=latest_message_id:
								new_GT_B = latest_message_id
								break
						
					
				except Exception as e:
					if "The channel specified is private and yo" in str(e):
						status_refresh_req_flag = True
					else:
						new_GT_B = i_temp
						print('Events handler error(GT handler mid): ', str(e))
					
				
				await GT_list_lock.acquire()
				try:
					if GTID in GT_list:
						GT_index = GT_list.index(GTID)
						GT_list_B[GT_index] = new_GT_B
						# print(str(GT_list_B[GT_index]))
				except Exception as e:
						print('Events handler error(GT handle stage2): ', str(e))
				finally:
					GT_list_lock.release()
	
	async def RC_event_handler(event_type,RCID,event_message):
		global RC_chat_id
		global RC_chat_last_id
		global RC_entity
		global ID_NAME
		try:
			
			while client.is_connected() == False:
				print("waiting for reconnect")
				await asyncio.sleep(60)
			
			if debug_mode:
				print("RC-H stage1"+str(RCID)+"....."+str(event_message.id))
				
			RCID = RCID
			date = event_message.date
			event_type = event_type
			msg_id = event_message.id
			
			if await check_record_exist(RCID,msg_id):
				return 0
			
			if event_message.from_id is not None:
				try:
					sender_id = int(str(event_message.from_id).split("=",1)[1].replace(")",""))
				except Exception as e:
					print('Events handler error(RC handler-1): ',str(e))
					
					await API_action_lock.acquire()
					try:
						sender_id = (await event_message.get_sender()).id
					finally:
						await asyncio.sleep(actionlock_release_interval)
						API_action_lock.release()
			else:
				sender_id = RCID
				# await API_action_lock.acquire()
				# try:
					# sender_id = (await event_message.get_sender()).id
				# finally:
					# await asyncio.sleep(actionlock_release_interval)
					# API_action_lock.release()
			from_name = ""
			if await check_id_name_db(str(sender_id)):
				from_name = (await get_id_name_db(str(sender_id)))[0]
			else:	
				from_name = str(await get_display_name_from_id(int(str(sender_id))))
				if from_name is None:
					from_name = "DeletedUser"
					await write_id_name_db(str(sender_id),"DeletedUser")
				else:
					await write_id_name_db(str(sender_id),from_name)
				
			topic = ""
			if event_message.reply_to:
				if event_message.reply_to.forum_topic:
					if str(event_message.reply_to.reply_to_top_id)=="None":
						topic = event_message.reply_to.reply_to_msg_id
					else:
						topic = event_message.reply_to.reply_to_top_id
				else:
					topic = ""
			else:
				topic = ""
			msg_type =""
			msg =""
			document_id=-1
			
			if debug_mode:
				print("RC-H stage2"+str(RCID)+"....."+str(event_message.id))
			
			if (not event_message.media) and event_message.message :
				msg_type = "msg"
				msg = event_message.message
			elif event_message.media and (not event_message.sticker) and (not event_message.poll) and (not event_message.audio) and (not event_message.voice):
				if hasattr(event_message.media, 'document') or hasattr(event_message.media,'photo'):
					msg_type = "media"
					msg = event_message.message
					await RC_mfd_lock.acquire()
					try:
						RC_chat_last_id = 0
						await msg_queue_H.put([7,RC_entity,event_message.id,event_message.to_id])
						while RC_chat_last_id == 0 or RC_chat_last_id == -2:
							await asyncio.sleep(0.1)
						document_id = RC_chat_last_id
					except Exception as e:
						print('Events handler error(RC handler)-2: ',str(e))
					finally:
						RC_mfd_lock.release()
				else:
					msg_type = "meida-OTH"
					msg = event_message.message
			
			elif event_message.media and event_message.sticker:
				msg_type = "sticker"
				msg = event_message.message
			elif event_message.media and event_message.poll:
				msg_type = "poll"
				msg = event_message.message
			elif event_message.media and event_message.audio:
				msg_type = "audio"
				msg = event_message.message
			elif event_message.media and event_message.voice:
				msg_type = "voice"
				msg = event_message.message
			else:
				msg_type = "OTH"
				msg = event_message.message
				
			if debug_mode:
				print("RC-H stage3"+str(RCID)+"....."+str(event_message.id))
				
			if await check_record_exist(RCID,event_message.id)==False:
				await add_new_msg(RCID,date,event_type,msg_id,sender_id,from_name,topic,msg_type,msg,document_id)
			
		except Exception as e:
			if "'NoneType' object has no attribute " in str(e):
				pass
			elif "disconnected" in str(e):
				raise ValueError(str(e))
			elif "DB fail" in str(e):
				raise ValueError(str(e))
			elif "int() argument must be a string, a bytes-like object or a real number, not 'PeerChannel'" in str(e):
				pass
			else:
				print('Events handler error(RC handler)-3: ', str(e))
	
	async def startup():
		global me_id
		global me_id_full
		global file_drive_entity
		global RC_entity
		global RC_chat_id
		try:
		
			me_id = (await client.get_me()).id
			me_id_full = await get_actual_peer(me_id)
			print("me: "+str(me_id_full))
			file_drive_entity = await client.get_entity(int("5612666796"))
			if RC_chat_id>0:
				RC_entity = await client.get_entity(RC_chat_id)
		except Exception as e:
			print('startup'+str(e))
	
	async def get_status(event):	
		global error_count
		global GT_list
		global GT_list_B
		global auto_forward_list
		global auto_forward_list_B
		global file_duplicate_count
		global message_record_list
		global extra_AF_list
		global RC_list
		global ID_NAME
		
	
		output = "".join([ "{0}: {1}\n".format(key,value) for (key, value) in in_progress.items()])
		#net speed
		S_rate = psutil.net_io_counters().bytes_recv
		await asyncio.sleep(1)
		E_rate = psutil.net_io_counters().bytes_recv
		net_rate = E_rate -S_rate
		net_rate = net_rate/1024./1024.
		
		if output: 
			output = "Active downloads:  "+ str(len(in_progress)) +"\n\n" + output 
		else: 
			output = "No active downloads"
		
		output = output+ "\n------------------------------------------------------------\nWaiting : " + str(queue.qsize())+ "   Fail: "+str(error_count)+"\nSpeed:  "+ str(net_rate)[0:5]+"Mb/s \nMQ: "+str(missing_msg_queue.qsize())+"\nFile duplicate: "+str(file_duplicate_count)+"\nGT_queue: "+str(GT_queue.qsize())
		output = output+"\n------------------------------------------------------------\nCount:\nAF   -> "+str(len(auto_forward_list))+"\nGT   -> "+str(len(GT_list))+"\nEXT -> "+str(len(extra_AF_list))+"\nRC   -> "+str(len(RC_list))
		output_af = ""
		output_af = output_af+"\n------------------------------------------------------------\nAF :"
		i = 0
		while i<len(auto_forward_list):
			try:
				display_name = str(await get_display_name_from_id(auto_forward_list[i]))				
				
				if await check_id_name_db(str(auto_forward_list[i])):
					pass
				else:	
					# display_name = str(await get_display_name_from_id(auto_forward_list[i]))
					await write_id_name_db(str(auto_forward_list[i]),display_name)
				
				if display_name =="The channel specified is private and you lack permission to access it" or display_name =="Deleted Account(bot)":
					raise ValueError("The channel specified is private and you lack permission to access it")
				output_af =output_af+"\n"+ str(auto_forward_list[i])+"->"+display_name+"("+str(auto_forward_list_B[i])+")"
			except Exception as e:
				#print("err:"+str(auto_forward_list[i]).replace("PeerChannel(channel_id=","").replace(")",""))
				#print("W:Some error occured while checking the status. Retry.("+str(e)+")")
				if "The channel specified is private and you lack permission to access it" in str(e):
					await remove_afd(auto_forward_list[i])
					i-=1
				else:
					print("staus GT:Some error occured while checking the status. Retry.("+str(e)+")")
			i+=1
			
			
		output_gt = ""
		output_gt = output_gt+"\n------------------------------------------------------------\nGT :"
		i = 0
		while i<len(GT_list):
			try:
				display_name = str(await get_display_name_from_id(GT_list[i]))				
				
				if await check_id_name_db(str(GT_list[i])):
					pass
				else:	
					# display_name = str(await get_display_name_from_id(GT_list[i]))
					await write_id_name_db(str(GT_list[i]),display_name)
				
				if display_name =="The channel specified is private and you lack permission to access it" or display_name =="Deleted Account(bot)":
					raise ValueError("The channel specified is private and you lack permission to access it")
				output_gt =output_gt+"\n"+ str(GT_list[i])+"->"+display_name+"("+str(GT_list_B[i])+")"
			except Exception as e:
				#print("err:"+str(auto_forward_list[i]).replace("PeerChannel(channel_id=","").replace(")",""))
				#print("W:Some error occured while checking the status. Retry.("+str(e)+")")
				if "The channel specified is private and you lack permission to access it" in str(e):
					await remove_GT(GT_list[i])
					i-=1
				else:
					print("staus GT:Some error occured while checking the status. Retry.("+str(e)+")")
			i+=1
			
		output_rc = ""
		output_rc = output_rc+"\n------------------------------------------------------------\nRC :"
		i = 0
		while i<len(RC_list):
			try:		
				display_name = str(await get_display_name_from_id(RC_list[i]))
				if await check_id_name_db(str(RC_list[i])):
					pass
				else:	
					# display_name = str(await get_display_name_from_id(RC_list[i]))
					await write_id_name_db(str(RC_list[i]),display_name)
				
				if display_name =="The channel specified is private and you lack permission to access it" or display_name =="Deleted Account(bot)":
					raise ValueError("The channel specified is private and you lack permission to access it")
				output_rc =output_rc+"\n"+ str(RC_list[i])+"->"+display_name+"("+str(RC_list_B[i])+")"
			except Exception as e:
				#print("err:"+str(auto_forward_list[i]).replace("PeerChannel(channel_id=","").replace(")",""))
				#print("W:Some error occured while checking the status. Retry.("+str(e)+")")
				if "The channel specified is private and you lack permission to access it" in str(e):
					await remove_RC(RC_list[i])
					i-=1
				else:
					print("staus GT:Some error occured while checking the status. Retry.("+str(e)+")")
			i+=1
				
				
		return output,output_af,output_gt,output_rc	
		
	async def load():
		await load_json()
		await load_sql()
		msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "config loaded"])
	
	async def save():
		save_state()
		await save_to_DB()
	
	async def auto_save():
		while True:
			await save_to_DB_fast()
			await asyncio.sleep(300)
	
	async def load_json():
		global GT_list
		global GT_list_B
		global auto_forward_list
		global auto_forward_list_B
		# global file_hash_list_md5
		# global file_hash_list_sha256
		global message_record_list
		global extra_AF_list
		global DB_info
		global RC_list
		global RC_list_B
		global RC_chat_id
		global ID_NAME
		
	
		tmp_lst = [[],[],[],[],[],[],[],extra_AF_list,DB_info,[],[],RC_chat_id,[]]
		try:
			with open("TG_auto_save.json", 'r') as f:
				data = json.load(f)
			save_lst = json.loads(data)
			_,_,_,_,_,_,_,extra_AF_list,DB_info,_,_,RC_chat_id,_ =save_lst
			
			print("json loaded")
			
				
			# if len(ID_NAME)==0:
				# ID_NAME=tmp_lst(12)
				
			await connect_DB()
			
			
			msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "json loaded"])
		except Exception as e:
			if "afd list A/B count mismatch" in str(e):
				print('load: ',str(e))
			if "GT list A/B count mismatch" in str(e):
				print('load: ',str(e))
			if "RC list A/B count mismatch" in str(e):
				print('load: ',str(e))
				
			else:
				_,_,_,_,_,_,_,extra_AF_list,DB_info,_,_,RC_chat_id,_ = tmp_lst
				msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "json load fail :"+ str(e)])	
			
	async def load_sql():
		global GT_list
		global GT_list_B
		global auto_forward_list
		global auto_forward_list_B
		# global file_hash_list_md5
		# global file_hash_list_sha256
		global message_record_list
		global extra_AF_list
		global DB_info
		global RC_list
		global RC_list_B
		global RC_chat_id
		global ID_NAME
		
	
		tmp_lst = [auto_forward_list,auto_forward_list_B,[],[],[],GT_list,GT_list_B,extra_AF_list,DB_info,RC_list,RC_list_B,RC_chat_id,[]]
		await afd_list_lock.acquire()
		await GT_list_lock.acquire()
		await RC_list_lock.acquire()
		try:
			
			auto_forward_list,auto_forward_list_B = await load_AF_db(me_id)
			GT_list,GT_list_B = await load_GT_db(me_id)
			RC_list,RC_list_B = await load_RC_db(me_id)
			
			if(len(auto_forward_list) ==len(auto_forward_list_B)):
				pass
			else:
				raise ValueError("afd list A/B count mismatch")
			
			if(len(GT_list) ==len(GT_list_B)):
				pass
			else:
				raise ValueError("GT list A/B count mismatch")
			
			if(len(RC_list) ==len(RC_list_B)):
				pass
			else:
				raise ValueError("RC list A/B count mismatch")
				
			# if len(ID_NAME)==0:
				# ID_NAME=tmp_lst(12)
				
			msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "sql loaded"])
		except Exception as e:
			if "afd list A/B count mismatch" in str(e):
				print('load: ',str(e))
			if "GT list A/B count mismatch" in str(e):
				print('load: ',str(e))
			if "RC list A/B count mismatch" in str(e):
				print('load: ',str(e))
				
			else:
				auto_forward_list,auto_forward_list_B,_,_,_,GT_list,GT_list_B,extra_AF_list,DB_info,RC_list,RC_list_B,RC_chat_id,_ = tmp_lst
				msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "sql load fail :"+ str(e)])	
		finally:
			afd_list_lock.release()
			GT_list_lock.release()
			RC_list_lock.release()
		
	async def status_refresh_wk():
		global status_refresh_req_flag
		
		await initail_lock.acquire()
		initail_lock.release()
		
		while 1==1:
			while status_refresh_req_flag ==False:
				await asyncio.sleep(300)
				
			await get_status([])
			
			status_refresh_req_flag =False
		
	async def disk_monitor():
		while 1==1:
			try:
				disk_lock = False
				disk_usage = psutil.disk_usage('/')
				available_percent = disk_usage.percent
				
				while available_percent < 10:
					disk_lock = False
					await downloader_lock_norm.acquire()
					await downloader_lock_GT.acquire()
					await asyncio.sleep(60)
					print("Disk space full,WK has stop!!")
					msg_queue_H.put_nowait([0,event, "Disk space full,WK has stop!!"])
					disk_lock =True
				try:
					if disk_lock:
						downloader_lock_norm.release()
						downloader_lock_GT.release()
				except:
					pass
				await asyncio.sleep(60)
			except Exception as e:
				print('disk monitor:',str(e))
	
	async def release_file_key_transfer():
		global file_KEY_transfer_lock
		
		while 1 ==1:
			try:
				file_KEY_transfer_lock =0
			except:
				pass
			await asyncio.sleep(3)
	
	def separate_file_code(file_code):
		file_code_list = re.split(r'(?<!\n)(vi_|p_|fd_|d_|fds_|pk_)', file_code)
		
		
		if len(file_code_list) > 1:
			file_code_list.pop(0)
			file_code_list = [file_code_list[i] + file_code_list[i+1] for i in range(0, len(file_code_list)-1, 2)]
			
			output_list = []
			for i in range(0,len(file_code_list)):
				output_key = file_code_list[i]
				if file_code_list[i].startswith("vi_") or file_code_list[i].startswith("p_") or file_code_list[i].startswith("d_"):
					while len(output_key)<50 and i<len(file_code_list)-1:
						output_key=output_key+file_code_list[i+1]
						i+=1
				if file_code_list[i].startswith("pk_") or file_code_list[i].startswith("fd_") or file_code_list[i].startswith("fds_"):
					while len(output_key)<30 and i<len(file_code_list)-1:
						output_key=output_key+file_code_list[i+1]
						i+=1
				output_list.append(output_key)
			
			
			return output_list
		else:
			return [file_code]
	
	def separate_file_code2(file_code):
		secret_keys = re.findall(r'((d_|p_|vi_)[A-Za-z0-9_-]{40,})|((fds_|pk_|fd_)[A-Za-z0-9_-]{20,})', file_code)
		
	def calculate_md5(file_path):
		global hash_chunk_size
		try:
			md5 = hashlib.md5()

			with open(file_path, 'rb') as file:
				while True:
					data = file.read(hash_chunk_size)
					if not data:
						break
					md5.update(data)
			return str(md5.hexdigest())
		except Exception as e:
			print('Events handler error(md5 hasher): ', str(e))
			return ""

	def calculate_sha256(file_path):
		global hash_chunk_size
		try:
			sha256 = hashlib.sha256()

			with open(file_path, 'rb') as file:
				while True:
					data = file.read(hash_chunk_size)
					if not data:
						break
					sha256.update(data)

			return str(sha256.hexdigest())
		except Exception as e:
			print('Events handler error(sha hasher): ', str(e))
			return ""
	
	def split_string(text, max_length): #4096
		parts = []
		while len(text) > max_length:
			# Find the last newline character within the allowed range
			idx = text.rfind('\n', 0, max_length)
			if idx == -1:  # If no newline found, split the string at max_length
				idx = max_length
			parts.append(text[:idx].strip())  # Add the substring to the parts list
			#print(text[:idx].strip())
			text = text[idx:]  # Update the remaining text
		if text:
			parts.append(text.strip())  # Add the remaining text if any
		return parts
	
	async def setDB(server,user,passsword,database):
		global DB_info
		global DB_conn
		
		DB_conn_tmp = DB_conn
		try:
			DB_conn = pymssql.connect(server=server,user=user,password=passsword,database=database,as_dict=True)
			init_DB()
			DB_info = [server,user,passsword,database]
			msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "set DB success"])
			return True
		except Exception as e:
			DB_conn = DB_conn_tmp
			msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "set DB fail"])
			print('setDB: '+str(e))
			return False
			
	async def connect_DB():
		global DB_info
		global DB_conn
		
		DB_conn_tmp = DB_conn
		await DB_action_lock.acquire()
		try:
			DB_conn = pymssql.connect(server=DB_info[0],user=DB_info[1],password=DB_info[2],database=DB_info[3],as_dict=True)
			print("DB connected")
			
			msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "DB connected"])
		except Exception as e:
			DB_conn = DB_conn_tmp
			msg_queue_H.put_nowait([6,await client.get_entity(robot_chat), "DB connect fail"])
			print('connect_DB: '+str(e))
		finally:
			DB_action_lock.release()
			
	async def check_db_conn():
		global DB_conn
		
		await DB_action_lock.acquire()
		DB_action_lock.release()
		try:
			SQL_QUERY = "SELECT * FROM ["+str(DB_info[3])+"].[dbo].[RC_summary] "
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_db_conn: '+str(e))
			return False
		
	def exec_sql(sql):
		pass
	
	async def create_new_chat(RCID,chat_name):
		global DB_conn
		
		await DB_action_lock.acquire()
		DB_action_lock.release()
		
		try:
			new_table_name = "chat_"+str(RCID)
			
			
			chat_name = str_formating(chat_name)
			
			# SQL_QUERY = "CREATE TABLE [dbo].["+new_table_name+"]([id] [int] IDENTITY(1,1) NOT NULL,[time] [timestamp] NULL,[date] [datetimeoffset](7) NULL,[event_type] [varchar](50) NOT NULL,[msg_id] [varchar](50) NOT NULL,[from_id] [varchar](50) NULL,[from_name] [nvarchar](max) NULL,[topic] [varchar](50) NULL,[msg_type] [varchar](50) NULL,[msg] [nvarchar](max) NULL,[document_id] [int] NULL,CONSTRAINT [PK_"+new_table_name+"] PRIMARY KEY CLUSTERED ([id] ASC)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]"
			# cursor = DB_conn.cursor()
			# cursor.execute(SQL_QUERY)
			# # result = cursor.fetchone()
			# DB_conn.commit()
			# print("table "+ new_table_name+" created")
			SQL_QUERY = "INSERT INTO [dbo].[RC_summary]([rcid],[rcname],[rc_dbname]) VALUES('"+str(RCID)+"',N'"+chat_name+"','"+new_table_name+"')"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			# result = cursor.fetchone()
			DB_conn.commit()
			print("table "+ new_table_name+" registed")
		except Exception as e:
			await connect_DB()
			print('create_new_chat: '+"query: "+SQL_QUERY+"error: "+str(e))
		
	async def add_new_msg(RCID,date,event_type,msg_id,from_id,from_name,topic,msg_type,msg,document_id):
		global DB_conn
		
		await DB_action_lock.acquire()
		DB_action_lock.release()
		
		try:
			table_name = "chat_"+str(RCID)
			msg = str_formating(msg)
			from_name = str_formating(from_name)
		except Exception as e:
			print('add_new_msg-1: '+"error: "+str(e))
			raise ValueError("DB fail")
			
		try:
			# SQL_QUERY = "INSERT INTO [dbo].["+table_name+"]([date],[event_type],[msg_id],[from_id],[from_name],[topic],[msg_type],[msg],[document_id]) VALUES('"+str(date)+"','"+str(event_type)+"','"+str(msg_id)+"','"+str(from_id)+"',N'"+str(from_name)+"','"+str(topic)+"','"+str(msg_type)+"',N'"+str(msg)+"','"+str(document_id)+"')"
			SQL_QUERY = "INSERT INTO [dbo].[chat_record]([date],[event_type],[to_id],[msg_id],[from_id],[from_name],[topic],[msg_type],[msg],[document_id],[document_afd_chat_id],[document_afd_chat2_id])VALUES('"+str(date)+"','"+str(event_type)+"','"+str(RCID)+"','"+str(msg_id)+"','"+str(from_id)+"',N'"+str(from_name)+"','"+str(topic)+"','"+str(msg_type)+"',N'"+str(msg)+"','"+str(document_id)+"','"+str(RC_chat_id)+"',NULL)"

			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('add_new_msg-2: '+"query: "+SQL_QUERY+"error: "+str(e))
			raise ValueError("DB fail")
		
	async def check_db_exist(RCID):
		global DB_conn
		
		await DB_action_lock.acquire()
		DB_action_lock.release()
		
		try:
			SQL_QUERY = "SELECT [rcid],[rc_dbname] FROM ["+str(DB_info[3])+"].[dbo].[RC_summary] WHERE [rcid]='"+str(RCID)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_db_exist: '+str(e))
			return False
	
	async def init_DB():
		global DB_conn
		
		await DB_action_lock.acquire()
		DB_action_lock.release()
		
		
		try:
			new_table_name = "RC_summary"
			
			SQL_QUERY = "CREATE TABLE [dbo].[RC_summary]([rid] [int] IDENTITY(1,1) NOT NULL,[rcid] [varchar](50) NOT NULL,[rcname] [nvarchar](max) NOT NULL,[rc_dbname] [varchar](50) NOT NULL,CONSTRAINT [PK_RC_summary] PRIMARY KEY CLUSTERED ([rid] ASC)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			# result = cursor.fetchone()
			DB_conn.commit()
			print("table "+ new_table_name+" created")
		except Exception as e:
			print('create_new_chat: '+str(e))
	
	async def check_record_exist(RCID,msg_id):
		global DB_conn
		
		await DB_action_lock.acquire()
		DB_action_lock.release()
		
		try:
			table_name = "chat_"+str(RCID)
			
			#SQL_QUERY = "SELECT [msg_id] FROM [TG_recordbot].[dbo].["+table_name+"] WHERE [msg_id]='"+str(msg_id)+"' AND [event_type]='new_message'"
			SQL_QUERY = "SELECT [id] FROM ["+str(DB_info[3])+"].[dbo].[chat_record] WHERE [to_id]='"+str(RCID)+"' AND [msg_id]='"+str(msg_id)+"' AND [event_type]='new_message'"
			
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_record_exist: '+str(e))
			return False
	
	async def save_to_DB():
		global auto_forward_list
		global auto_forward_list_B
		
		global GT_list
		global GT_list_B
		
		global extra_AF_list
		
		global RC_list
		global RC_list_B
		
		global file_hash_list_md5
		global file_hash_list_sha256
		global message_record_list
		
		global ID_NAME
	
		if await check_db_conn():
			#AF
			for i in range(0,len(auto_forward_list)):
				name = "--"
				try:
					name = await get_display_name_from_id(auto_forward_list[i])
				except:
					pass
					
				if await check_AF_db(auto_forward_list[i]):
					if await check_AF_force_db(auto_forward_list[i],me_id):
						await update_AF_db(auto_forward_list[i],name,auto_forward_list_B[i],me_id)
					else:
						await write_AF_db(auto_forward_list[i],name,auto_forward_list_B[i],me_id)
				else:
					await write_AF_db(auto_forward_list[i],name,auto_forward_list_B[i],me_id)
				
			#GT
			for i in range(0,len(GT_list)):
				name = "--"
				try:
					name = await get_display_name_from_id(GT_list[i])
				except:
					pass
					
				if await check_GT_db(GT_list[i]):
					if await check_GT_force_db(GT_list[i],me_id):
						await update_GT_db(GT_list[i],name,GT_list_B[i],me_id)
					else:
						await write_GT_db(GT_list[i],name,GT_list_B[i],me_id)
				else:
					await write_GT_db(GT_list[i],name,GT_list_B[i],me_id)
			#EXT
			#RC
			for i in range(0,len(RC_list)):
				name = "--"
				try:
					name = await get_display_name_from_id(RC_list[i])
				except:
					pass
					
				if await check_RC_db(RC_list[i]):
					if await check_RC_force_db(RC_list[i],me_id):
						await update_RC_db(RC_list[i],name,RC_list_B[i],me_id)
					else:
						await write_RC_db(RC_list[i],name,RC_list_B[i],me_id)
				else:
					await write_RC_db(RC_list[i],name,RC_list_B[i],me_id)
			
			#hash
			for md5 in file_hash_list_md5:
				if await check_hash_db(md5,""):
					pass
				else:
					await write_to_hash_db(md5,"")
			
			#msg
			for msg in message_record_list:
				if await check_afd_msg_history(msg):
					pass
				else:
					await write_to_msg_history_db(msg)
					
			#ID_NAME
			for ID in ID_NAME:
				if await check_id_name_db(ID):
					print((await get_id_name_db(ID))[0])
				else:
					await write_id_name_db(ID,ID_NAME[ID])
		
		print("saved to db")
		
	async def save_to_DB_fast():
		global auto_forward_list
		global auto_forward_list_B
		
		global GT_list
		global GT_list_B
		
		global extra_AF_list
		
		global RC_list
		global RC_list_B
		
		global file_hash_list_md5
		global file_hash_list_sha256
		global message_record_list
		
		global ID_NAME
	
		if await check_db_conn():
			#AF
			for i in range(0,len(auto_forward_list)):
				name = "--"
					
				if await check_AF_db(auto_forward_list[i]):
					if await check_AF_force_db(auto_forward_list[i],me_id):
						await update_AF_db(auto_forward_list[i],name,auto_forward_list_B[i],me_id)
					else:
						await write_AF_db(auto_forward_list[i],name,auto_forward_list_B[i],me_id)
				else:
					await write_AF_db(auto_forward_list[i],name,auto_forward_list_B[i],me_id)
				
			#GT
			for i in range(0,len(GT_list)):
				name = "--"
					
				if await check_GT_db(GT_list[i]):
					if await check_GT_force_db(GT_list[i],me_id):
						await update_GT_db(GT_list[i],name,GT_list_B[i],me_id)
					else:
						await write_GT_db(GT_list[i],name,GT_list_B[i],me_id)
				else:
					await write_GT_db(GT_list[i],name,GT_list_B[i],me_id)
			#EXT
			#RC
			for i in range(0,len(RC_list)):
				name = "--"
					
				if await check_RC_db(RC_list[i]):
					if await check_RC_force_db(RC_list[i],me_id):
						await update_RC_db(RC_list[i],name,RC_list_B[i],me_id)
					else:
						await write_RC_db(RC_list[i],name,RC_list_B[i],me_id)
				else:
					await write_RC_db(RC_list[i],name,RC_list_B[i],me_id)
			
			#hash
			for md5 in file_hash_list_md5:
				if await check_hash_db(md5,""):
					pass
				else:
					await write_to_hash_db(md5,"")
			
			#msg
			for msg in message_record_list:
				if await check_afd_msg_history(msg):
					pass
				else:
					await write_to_msg_history_db(msg)
					
			#ID_NAME
			for ID in ID_NAME:
				if await check_id_name_db(ID):
					print((await get_id_name_db(ID))[0])
				else:
					await write_id_name_db(ID,ID_NAME[ID])
		
	async def check_fileid_db(file_id):
	
		try:
			file_id = str_formating(file_id)
		except:
			print('check_fileid_db-1: '+"error: "+str(e))
			raise ValueError("DB fail")
			
		try:
			SQL_QUERY = "SELECT [file_id] FROM [dbo].[file_id] WHERE file_id = '"+str(file_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_fileid_db-2: '+str(e))
			return False
			
	async def write_fileid_db(file_id):
	
		try:
			file_id = str_formating(file_id)
		except:
			print('write_fileid_db-1: '+"error: "+str(e))
			raise ValueError("DB fail")
		
		try:
			SQL_QUERY = "INSERT INTO [dbo].[file_id]([file_id]) VALUES('"+file_id+"')"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			if "Cannot insert duplicate key row in object" in str(e):
				pass
			else:
				await connect_DB()
				raise ValueError("DB fail")
			print('write_fileid_db-2: '+"query: "+SQL_QUERY+"error: "+str(e))
			
	async def remove_fileid_db(file_id):
		try:
			file_id = str_formating(file_id)
		except:
			print('remove_fileid_db-1: '+"error: "+str(e))
			raise ValueError("DB fail")
		
		try:
			SQL_QUERY = "DELETE FROM [dbo].[file_id] WHERE [FILE_ID]  = '"+file_id+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			if "Cannot insert duplicate key row in object" in str(e):
				pass
			else:
				await connect_DB()
				raise ValueError("DB fail")
			print('remove_fileid_db-2: '+"query: "+SQL_QUERY+"error: "+str(e))
			
	async def check_hash_db(md5,sha256):
		try:
			hash = hashlib.sha256()
			hash.update(str(md5+md5+sha256+md5+sha256).encode('utf-8'))
			hash = str(hash.hexdigest())
		except Exception as e:
			print('check_db_exist-1: '+str(e))
			
	
		try:
			# SQL_QUERY = "SELECT [id],[md5],[sha256]FROM [dbo].[hash] WHERE md5 = '"+md5+"' and sha256='"+sha256+"'"
			SQL_QUERY = "SELECT [id],[hash] FROM [dbo].[hash] WHERE hash = '"+hash+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_db_exist-2: '+str(e))
			return False
	
	async def check_afd_msg_history(msg):
		try:
			msg = str_formating(msg)
		except Exception as e:
			print('check_afd_msg_history-1: '+"error: "+str(e))
			raise ValueError("DB fail")
			
		try:
			SQL_QUERY = "SELECT [id]FROM [dbo].[list_afd_msg_history] WHERE msg = N'"+msg+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_afd_msg_history-2: '+str(e))
			return False
	
	async def get_id_name_db(ID):
		try:
			SQL_QUERY = "SELECT [id],[peerid],[peername] FROM [dbo].[id_name] WHERE peerid ='"+str(ID)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return [str(records[0]["peername"])]
			else:
				return [""]
		except Exception as e:
			print('get_id_name_db: '+str(e))
			return [""]
			
	async def check_id_name_db(ID):
		try:
			SQL_QUERY = "SELECT [id],[peerid],[peername] FROM [dbo].[id_name] WHERE peerid ='"+str(ID)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_id_name_db: '+str(e))
			return False
		
	async def write_to_hash_db(md5,sha256):
		try:
			hash = hashlib.sha256()
			hash.update(str(md5+md5+sha256+md5+sha256).encode('utf-8'))
			hash = str(hash.hexdigest())
		except Exception as e:
			print('write_to_hash_db-1: '+str(e))
	
		try:
			# SQL_QUERY = "INSERT INTO [dbo].[hash]([md5],[sha256]) VALUES('"+md5+"' ,'"+sha256+"')"
			SQL_QUERY = "INSERT INTO [dbo].[hash]([hash]) VALUES('"+hash+"')"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			if "Cannot insert duplicate key row in object" in str(e):
				pass
			else:
				await connect_DB()
				raise ValueError("DB fail")
			print('add_new_msg-2: '+"query: "+SQL_QUERY+"error: "+str(e))
		
	async def write_to_msg_history_db(msg):
		try:
			msg = str_formating(msg)
		except Exception as e:
			print('write_to_msg_history_db-1: '+"error: "+str(e))
			raise ValueError("DB fail")
			
		try:
			SQL_QUERY = "INSERT INTO [dbo].[list_afd_msg_history]([msg]) VALUES(N'"+msg+"')"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('write_to_msg_history_db-2: '+"query: "+SQL_QUERY+"error: "+str(e))
			raise ValueError("DB fail")
	
	async def write_id_name_db(ID,name):
		
		if len(name)==0:
			return 0
		
		try:
			name = str_formating(name)
		except Exception as e:
			print('write_id_name_db-1: '+"error: "+str(e))
			raise ValueError("DB fail")
			
		try:
			SQL_QUERY = "INSERT INTO [dbo].[id_name]([peerid],[peername]) VALUES('"+str(ID)+"' ,N'"+str(name)+"')"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			if "Cannot insert duplicate key row in object" in str(e):
				pass
			else:
				await connect_DB()
				raise ValueError("DB fail")
			print('write_id_name_db-2: '+"query: "+SQL_QUERY+"error: "+str(e))
			
	async def check_AF_db(ID):
		try:
			SQL_QUERY = "SELECT [id] FROM [dbo].[list_af] WHERE afid = N'"+str(ID)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_AF_db: '+str(e))
			return False
	
	async def check_RC_db(ID):
		try:
			SQL_QUERY = "SELECT [id] FROM [dbo].[list_rc] WHERE rcid = N'"+str(ID)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_RC_db: '+str(e))
			return False
	
	async def check_GT_db(ID):
		try:
			SQL_QUERY = "SELECT [id] FROM [dbo].[list_gt] WHERE gtid = N'"+str(ID)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_GT_db: '+str(e))
			return False
	
	async def check_AF_force_db(ID,bot_id):
		try:
			SQL_QUERY = "SELECT [id] FROM [dbo].[list_af] WHERE afid = N'"+str(ID)+"' AND bot_id = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_AF_force_db: '+str(e))
			return False
	
	async def check_GT_force_db(ID,bot_id):
		try:
			SQL_QUERY = "SELECT [id] FROM [dbo].[list_gt] WHERE gtid = N'"+str(ID)+"' AND bot_id = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_GT_force_db: '+str(e))
			return False
			
	async def check_RC_force_db(ID,bot_id):
		try:
			SQL_QUERY = "SELECT [id] FROM [dbo].[list_rc] WHERE rcid = N'"+str(ID)+"' AND bot_id = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				return True
			else:
				return False
		except Exception as e:
			print('check_RC_force_db: '+str(e))
			return False
	
	async def update_AF_db(ID,name,count,bot_id):
		try:
			name = str_formating(name)
			if name=="--":
				SQL_QUERY = "UPDATE [dbo].[list_af] SET [proccess_count] = '"+str(count)+"' WHERE [afid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			else:
				SQL_QUERY = "UPDATE [dbo].[list_af] SET [afname] = N'"+str(name)+"',[proccess_count] = '"+str(count)+"' WHERE [afid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('update_AF_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			
	async def update_GT_db(ID,name,count,bot_id):
		try:
			name = str_formating(name)
			if name=="--":
				SQL_QUERY = "UPDATE [dbo].[list_gt] SET [proccess_count] = '"+str(count)+"' WHERE [gtid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			else:
				SQL_QUERY = "UPDATE [dbo].[list_gt] SET [gtname] = N'"+str(name)+"',[proccess_count] = '"+str(count)+"' WHERE [gtid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('update_GT_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			
	async def update_RC_db(ID,name,count,bot_id):
		try:
			name = str_formating(name)
			if name=="--":
				SQL_QUERY = "UPDATE [dbo].[list_rc] SET [proccess_count] = '"+str(count)+"' WHERE [rcid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			else:
				SQL_QUERY = "UPDATE [dbo].[list_rc] SET [rcname] = N'"+str(name)+"',[proccess_count] = '"+str(count)+"' WHERE [rcid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('update_RC_db: '+"query: "+SQL_QUERY+"error: "+str(e))
	
	async def update_AF2_db(ID,count,bot_id):
		try:
			name = str_formating(name)
			SQL_QUERY = "UPDATE [dbo].[list_af] SET [proccess_count] = '"+str(count)+"' WHERE [afid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('update_AF2_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			
	async def update_GT2_db(ID,count,bot_id):
		try:
			name = str_formating(name)
			SQL_QUERY = "UPDATE [dbo].[list_af] SET [proccess_count] = '"+str(count)+"' WHERE [gtid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('update_GT2_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			
	async def update_RC2_db(ID,count,bot_id):
		try:
			name = str_formating(name)
			SQL_QUERY = "UPDATE [dbo].[list_rc] SET [proccess_count] = '"+str(count)+"' WHERE [rcid] = '"+str(ID)+"' AND [bot_id] = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('update_RC2_db: '+"query: "+SQL_QUERY+"error: "+str(e))
	
	async def write_AF_db(ID,name,count,bot_id):
		try:
			name = str_formating(name)
			SQL_QUERY = "INSERT INTO [dbo].[list_af]([afid],[afname],[proccess_count],[bot_id]) VALUES('"+str(ID)+"', N'"+str(name)+"','"+str(count)+"','"+str(bot_id)+"')"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('write_AF_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			raise ValueError("DB fail")
			
	async def write_GT_db(ID,name,count,bot_id):
		try:
			name = str_formating(name)
			SQL_QUERY = "INSERT INTO [dbo].[list_gt]([gtid],[gtname],[proccess_count],[bot_id]) VALUES('"+str(ID)+"', N'"+str(name)+"','"+str(count)+"','"+str(bot_id)+"')"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('write_GT_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			raise ValueError("DB fail")
			
	async def write_RC_db(ID,name,count,bot_id):
		try:
			name = str_formating(name)
			SQL_QUERY = "INSERT INTO [dbo].[list_rc]([rcid],[rcname],[proccess_count],[bot_id]) VALUES('"+str(ID)+"', N'"+str(name)+"','"+str(count)+"','"+str(bot_id)+"')"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('write_RC_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			raise ValueError("DB fail")
			
	async def read_AF_setting_db(ID,bot_id):
		if_media= True
		if_link = True
		if_fkey = True
		if_me = True
		if_filter = True
		if_dedupe = True
		try:
			SQL_QUERY = "SELECT [id],[media],[link],[fkey],[me],[filter],[dedupe] FROM [dbo].[list_af] WHERE afid = '"+str(ID)+"' AND bot_id = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				if records[0]["media"] ==1:
					if_media = True
				else:
					if_media = False
				
				if records[0]["link"] ==1:
					if_link = True
				else:
					if_link = False
					
				if records[0]["fkey"] ==1:
					if_fkey = True
				else:
					if_fkey = False
					
				if records[0]["me"] ==1:
					if_me = True
				else:
					if_me = False
					
				if records[0]["filter"] ==1:
					if_filter = True
				else:
					if_filter = False
					
				if records[0]["dedupe"] ==1:
					if_dedupe = True
				else:
					if_dedupe = False
					
				
				return if_media,if_link,if_fkey,if_me,if_filter,if_dedupe
			else:
				return if_media,if_link,if_fkey,if_me,if_filter,if_dedupe
		except Exception as e:
			print('read_AF_setting_db: '+str(e))
			return if_media,if_link,if_fkey,if_me,if_filter,if_dedupe
			
	async def write_AF_setting_db(ID,if_media,if_link,if_fkey,if_me,if_filter,if_dedupe,bot_id):
		
		if if_media == True:
			if_media_code =1
		else:
			if_media_code =0
		
		if if_link == True:
			if_link_code =1
		else:
			if_link_code =0
			
		if if_fkey == True:
			if_fkey_code =1
		else:
			if_fkey_code =0
			
		if if_me == True:
			if_me_code =1
		else:
			if_me_code =0
			
		if if_filter == True:
			if_filter_code =1
		else:
			if_filter_code =0
			
		if if_dedupe == True:
			if_dedupe_code =1
		else:
			if_dedupe_code =0
		
		try:
			SQL_QUERY = "UPDATE [dbo].[list_af] SET [media] = '"+str(if_media_code)+"' ,[link] = '"+str(if_link_code)+"',[fkey] = '"+str(if_fkey_code)+"',[me] = '"+str(if_me_code)+"',[filter] = '"+str(if_filter_code)+"',[dedupe] = '"+str(if_dedupe_code)+"' WHERE [afid] = '"+str(ID)+"' AND bot_id = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			if "Cannot insert duplicate key row in object" in str(e):
				pass
			else:
				await connect_DB()
				raise ValueError("DB fail")
			print('write_AF_setting_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			
	async def get_replace_rule():
		rule_list = []
		try:
			SQL_QUERY = "SELECT [match_str],[replace_str]FROM [dbo].[replace_table]"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				for rule in records:
					rule_list.append([str(rule["match_str"]),str(rule["replace_str"])])
				return rule_list
			else:
				return rule_list
		except Exception as e:
			print('get_replace_rule: '+str(e))
			return rule_list
	
	async def apply_replace_rule(msg):
		rule_list = await get_replace_rule()
		
		for rule in rule_list:
			msg = msg.replace(rule[0],rule[1])
			
		return msg
		
	async def remove_AF_db(ID,bot_id):
		try:
			SQL_QUERY = "DELETE FROM [dbo].[list_af] WHERE afid = '"+str(ID)+"' AND bot_id= '"+str(bot_id)+"'"
			# print(SQL_QUERY)
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('remove_AF_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			raise ValueError("DB fail")
	
	async def remove_GT_db(ID,bot_id):
		try:
			SQL_QUERY = "DELETE FROM [dbo].[list_gt] WHERE gtid = '"+str(ID)+"' AND bot_id= '"+str(bot_id)+"'"
			# print(SQL_QUERY)
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('remove_GT_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			raise ValueError("DB fail")
			
	async def remove_RC_db(ID,bot_id):
		try:
			SQL_QUERY = "DELETE FROM [dbo].[list_rc] WHERE rcid = '"+str(ID)+"' AND bot_id= '"+str(bot_id)+"'"
			# print(SQL_QUERY)
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
		except Exception as e:
			await connect_DB()
			print('remove_RC_db: '+"query: "+SQL_QUERY+"error: "+str(e))
			raise ValueError("DB fail")
	
	async def get_AF_db(ID,bot_id):
		try:
			SQL_QUERY = "SELECT [afid],[proccess_count]FROM [dbo].[list_af] WHERE afid = '"+ID+"' AND bot_id= '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
			records = cursor.fetchall()
			if len(records) >0:
				return records[0]["proccess_count"]
		except Exception as e:
			print('get_AF_db: '+str(e))
			await connect_DB()
			
	async def get_GT_db(ID,bot_id):
		try:
			SQL_QUERY = "SELECT [gtid],[proccess_count]FROM [dbo].[list_gt] WHERE gtid = '"+ID+"' AND bot_id= '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
			records = cursor.fetchall()
			if len(records) >0:
				return records[0]["proccess_count"]
		except Exception as e:
			print('get_GT_db: '+str(e))
			await connect_DB()
			
	async def get_RC_db(ID,bot_id):
		try:
			SQL_QUERY = "SELECT [rcid],[proccess_count]FROM [dbo].[list_rc] WHERE rcid = '"+ID+"' AND bot_id= '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			DB_conn.commit()
			records = cursor.fetchall()
			if len(records) >0:
				return records[0]["proccess_count"]
		except Exception as e:
			print('get_RC_db: '+str(e))
			await connect_DB()
	
	async def load_AF_db(bot_id):
		try:
			SQL_QUERY = "SELECT [id],[afid],[proccess_count] FROM [dbo].[list_af] WHERE bot_id = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				id_list = []
				count_list = []
				for i in range(len(records)):
					try:
						id_list.append(int(str(records[i]["afid"])))
						count_list.append(int(str(records[i]["proccess_count"])))
					except Exception as e:
						print('load_AF_db-1: '+str(e))
					
				return[id_list,count_list]
			else:
				return [[],[]]
		except Exception as e:
			print('load_AF_db: '+str(e))
			raise ValueError("load AF error")
	
	async def load_GT_db(bot_id):
		try:
			SQL_QUERY = "SELECT [id],[gtid],[proccess_count] FROM [dbo].[list_gt] WHERE bot_id = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				id_list = []
				count_list = []
				for i in range(len(records)):
					try:
						id_list.append(int(str(records[i]["gtid"])))
						count_list.append(int(str(records[i]["proccess_count"])))
					except Exception as e:
						print('load_GT_db-1: '+str(e))
					
				return[id_list,count_list]
			else:
				return [[],[]]
		except Exception as e:
			print('load_GT_db: '+str(e))
			raise ValueError("load GT error")
			
	async def load_RC_db(bot_id):
		try:
			SQL_QUERY = "SELECT [id],[rcid],[proccess_count] FROM [dbo].[list_rc] WHERE bot_id = '"+str(bot_id)+"'"
			cursor = DB_conn.cursor()
			cursor.execute(SQL_QUERY)
			records = cursor.fetchall()
			if len(records) >0:
				id_list = []
				count_list = []
				for i in range(len(records)):
					try:
						id_list.append(int(str(records[i]["rcid"])))
						count_list.append(int(str(records[i]["proccess_count"])))
					except Exception as e:
						print('load_RC_db-1: '+str(e))
					
				return[id_list,count_list]
			else:
				return [[],[]]
		except Exception as e:
			print('load_RC_db: '+str(e))
			raise ValueError("load RC error")
	
	def str_formating(input):
		special_characters = {
			"'": "''",    # Single Quote
			"\\": "\\\\", # Backslash
			"%": "\\%",   # Percent Sign
			"_": "\\_",   # Underscore
			# Add more special characters as needed
		}
		output = str(input)
		try:
			if len(output)>0:
				for char, escaped_char in special_characters.items():
					output = output.replace(char, escaped_char)
				output = output.replace('"', '')
				output = output.replace('&', '')
		except  Exception as e:
			print('str formating: input: '+str(input)+" error:" +str(e))
			return input
		return output
	
	async def start():
		global client
		global ignore_forward_list
		
		if not os.path.exists("../collect"):
			os.makedirs("../collect")
		if not os.path.exists(downloadFolder):
			os.makedirs(downloadFolder)
		if not os.path.exists(tempFolder):
			os.makedirs(tempFolder)
			
		sqlconn = sqlite3.connect('record.db')

		client_start_time =time.time()
		if_first = True
		client_keep =True
			
		while if_first or (client_keep and client_start_time - time.time()>3600):
			if_first = False
			client_start_time =time.time()
			try:
				tasks = []
				ignore_forward_list = []
				# client = TelegramClient(getSession(), api_id, api_hash,proxy=proxy,auto_reconnect=True,retry_delay= 60,connection_retries= 5)
				
				await initail_lock.acquire()
				await client.start()
				
				# try:
					# await client.disconnected
				# except Exception as e:
					# print('daemon main loop-1:',str(e))
				try:
					await asyncio.sleep(5)
					await client.connect()
				except Exception as e:
					client_keep =False
					print('daemon main loop-2:',str(e))
					
				while client.is_connected() == False:
					raise ValueError("restart fail")
					
				loop = asyncio.get_event_loop()
				for i in range(worker_count):
					task = loop.create_task(worker())
					tasks.append(task)
				for i in range(worker_count):
					task = loop.create_task(GT_worker())
					tasks.append(task)
				task = loop.create_task(msg_transfer_worker())
				tasks.append(task)
				task = loop.create_task(RC_media_worker_sub())
				tasks.append(task)
				task = loop.create_task(msg_fill_worker())
				tasks.append(task)
				task = loop.create_task(status_refresh_wk())
				tasks.append(task)
				task = loop.create_task(disk_monitor())
				tasks.append(task)
				task = loop.create_task(release_file_key_transfer())
				tasks.append(task)
				await sendHelloMessage(client, robot_chat)
				print("inizialize...")
				await startup()
				print("load setting...")
				await load()
				print("inizialize...")
				await startup()
				print("get actual peer...")
				await get_status([])
				task = loop.create_task(auto_save())
				tasks.append(task)
				try:
					initail_lock.release()
					downloader_lock_norm.release()
					downloader_lock_GT.release()
				except Exception as e:
					if "Lock is not acquired." in str(e):
						pass
					else:
						print('initail lock release fail:',str(e))
				print("pre forward...")
				await pre_forward()
				print("inizialize finished...")
				try:
					await client.run_until_disconnected()
				except Exception as e:
					print('daemon main loop-3:',str(e))
				finally:
					pass

				for task in tasks:
					task.cancel()
				await asyncio.gather(*tasks, return_exceptions=True)
				await save()
				await asyncio.sleep(30)
			except Exception as e:
				print('daemon main loop:',str(e))
				await save()
		
		# Commit the changes and close the connection
		sqlconn.commit()
		sqlconn.close()
	
	try:
		client.loop.run_until_complete(start())
	except Exception as e:
		print('daemon main:',str(e))
	time.sleep(30)
