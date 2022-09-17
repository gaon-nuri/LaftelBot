#!/usr/bin python3

"""
라프텔 텔레그램 알리미.

신작 및 차회 등록 알림.

중지는 Ctrl + C.
"""

import os			# 환경
import requests		# 요청
import logging		# 로그
import html
import json
import traceback	# 추적
import laftel		# API
	

# 텔레그램 API
from telegram import (
	Update,					# 갱신
	ParseMode,				# 파서
	InlineKeyboardButton,	# 버튼
	InlineKeyboardMarkup,	# 메뉴
	ReplyKeyboardMarkup,	# 대화 1
	ReplyKeyboardRemove,	# 대화 2
)
# InlineQueryResultArticle, InputTextMessageContent


# PTB 프레임워크
from telegram.ext import (
	Updater,				# 갱신
	CommandHandler,			# 명령
	MessageHandler,			# 문자
	Filters,				# 필터
	CallbackContext,		# 답장
	CallbackQueryHandler,	# 입력
	ConversationHandler,	# 대화
)


# 환경 변수
from dotenv import load_dotenv
load_dotenv(verbose=True)


# 웹 크롤링
from bs4 import BeautifulSoup as bs

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s -\
							%(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# 대화 상태
SRT, WRK, SEL, JOB, CMP = range(5)


# 명령어 정의 : update, context 인수 필요

# 시작
def start(update, context) -> int:
	user = update.message.from_user
	logger.info("사용자 %s가 대화를 시작.", user.name)
	key = [
		[
			InlineKeyboardButton("신작", callback_data="신작"),
			InlineKeyboardButton("차회", callback_data="차회"),
		],
		[InlineKeyboardButton("안내", callback_data="안내")],
		[InlineKeyboardButton("닫기", callback_data="닫기")],
	]
	reply_markup = InlineKeyboardMarkup(key)
	update.message.reply_text("하나를 선택해 주세요", reply_markup =\
							  reply_markup)
	return SRT


# 재시작
def start_over(update, context) -> int:
	"같은 내용과 버튼을 다시 표시"
	query = update.callback_query
	query.answer()
	key = [
		[InlineKeyboardButton("알림", callback_data="알림")],
		[InlineKeyboardButton("안내", callback_data="안내")],
		[InlineKeyboardButton("닫기", callback_data="닫기")],
	]
	reply_markup = InlineKeyboardMarkup(key)
	query.edit_message_text("하나를 선택해 주세요", reply_markup =\
							  reply_markup)
	return SRT


# 안내
def helps(update, context) -> None:
	"명령어 안내 메시지 전송"
	text = "신작은 '/new', 차회는 '/ep'를 입력해 보세요."
	update.message.reply_text(text)


# 안내 버튼
def cb_help(update, context) -> None:
	"명령어를 소개"
	query = update.callback_query
	query.answer()
	
	text = "신작은 '/new', 차회는 '/ep'를 입력해 보세요."
	query.edit_message_text(text)

	# 메뉴로
	goback()


# 앵무새
def echo(update, context) -> None:
	update.message.reply_text(update.message.text)

echo_handler = MessageHandler(Filters.text & ~Filters.command, echo)


# 복귀
def goback(update, context) -> int:
	"시작 메뉴로 돌아갈지 질문"
	query = update.callback_query
	query.answer()

	key = [
		[InlineKeyboardButton("메뉴", callback_data="시작")],
		[InlineKeyboardButton("닫기", callback_data="닫기")],
	]
	reply_markup = InlineKeyboardMarkup(key)
	query.edit_message_text("하나를 선택해 주세요", reply_markup =\
							  reply_markup)
	return CMP

# 알림 버튼
def cb_alert(update, context) -> int:
	query = update.callback_query
	query.answer()

	# 안내문 전송
	text = "애니 이름을 입력하세요."
	query.edit_message_text(text)

	return WRK

	# 상태 : 검색 중
	context.bot.sendChatAction(
			chat_id=query.from_user,
			action=ChatAction.FIND_LOCATION,
	)

	data = update.message.text

	# 라프텔 이름 검색
	items = laftel.sync.searchAnime(data)
	
	# 상태 : 입력 중
	context.bot.sendChatAction(
			chat_id=query.from_user,
			action=ChatAction.TYPING,
	)

	# 검색 결과를 버튼으로
	key = []
	for i, item in enumerate(items):
		key.append([InlineKeyboardButton(
					f"{item.name}\n",
					callback_data = f"{i}"
					)])

	# 원하는 애니를 선택
	reply_markup = InlineKeyboardMarkup(key)
	text = "하나를 선택해 주세요."
	query.edit_message_text(text, reply_markup=reply_markup)

	# 상태 표시 후 종료
	text = "작품 페이지 검색 중..."
	query.edit_message_text(text)

	return SEL


# 작업 선택
def cb_sel(update, context) -> int:
	"신작과 차회 알림 중 택 1"
	query = update.callback_query
	query.answer()
	data = query.data

	# from datetime import date

	# 라프텔 작품 페이지
	url = items[int(data)].url # "https://laftel.net/item/40902"
	res = requests.get(url)

	# HTML 파싱
	soup = bs(res.content, 'html.parser')
	a = soup.select_one("title").text.rstrip('- 라프텔')

	# 회차 정보 추출
	eps = soup.select("h5")
	d = "" # date.today().isoformat().replace("-", ".")

	key = [
		[InlineKeyboardButton("신작", callback_data="신작")],
		[InlineKeyboardButton("차회", callback_data = "차회")],
	]

	# 원하는 작업을 선택
	reply_markup = InlineKeyboardMarkup(key)
	text = "하나를 선택해 주세요."
	query.edit_message_text(text, reply_markup=reply_markup)

	return JOB


# 신작 여부
def cb_new(update, context) -> int:
	"한 편도 없으면 꽝, 1화만 있으면 신작, 2화도 있으면 구작"
	
	# 한 편도 없음
	if len(eps) < 1:
		s = "은/는 아직이에요."

	# 1화만 있음
	elif len(eps) < 2:
		d = "조금 전"; s = "이/가 {D}에 나왔어요!".format(D=d)

	# 2화도 있음
	else:
		d = "오래 전"; s = "이/가 {D}에 나왔어요!".format(D=d)

	query.edit_message_text("{A}{S}".format(A=a, S=s))

	# 메뉴로
	goback()


# 차회 유무
def cb_ep(update, context) -> int:
	n = 11; t = "{A} {N}화".format(A=a, N=n)

	for ep in eps:
		# 차회 O
		if "{N}화".format(N=n+1) in ep.text:
			s = "나왔습니다!"
			query.edit_message_text("{T}가 {S}".format(T=t, S=s))
			exit()

	# 차회 X
	s = "아직입니다."
	query.edit_message_text("{T}는 {S}".format(T=t, S=s))

	# 메뉴로
	goback()


# 대화 종료
def cb_cancel(update, context) -> int:
	"대화 처리기에 종료 신호를 전송"
	query = update.callback_query
	query.answer()
	query.edit_message_text("다음에 또 이야기하자.")

	return ConversationHandler.END


# 틀린 명령
def unknown(update, context) -> None:
	update.message.reply_text("잘못된 명령어")


# 오류 처리
def error_handler(update: object, context) -> None:
	"오류 로그를 전송"
	logger.error(msg="갱신 처리 중 예외 발생:\n", exc_info=context.error)

	# 파이썬 오류 메시지
	tb_list = traceback.format_exception(None, context.error,\
										 context.error.__traceback__)
	tb_string = ''.join(tb_list)

	up_str = update.to_dict() if isinstance(update, Update)\
				 else str(update)
	
	# 메시지에 마크업과 추가 정보 넣기
	info_list = [
		f"갱신 처리 중 예외 발생",
		f"<pre>update = {html.escape(json.dumps(up_str, indent=2, ensure_ascii=False))}</pre>",
		f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>",
	]
	info_list2 = [
		f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>",
		f"<pre>{html.escape(tb_string)}</pre>",
	]

	chat_id = os.environ.get("DEV_ID")
	mode = ParseMode.HTML

	info = "\n".join(info_list)
	info2 = "\n".join(info_list2)

	# 메시지 전송
	# 너무 길면 나눠서
	if len(info) + len(info2) > 4096:
		context.bot.scancelMessage(chat_id=chat_id, text=info,\
								parse_mode=mode)	
		context.bot.scancelMessage(chat_id=chat_id, text=info2,\
								parse_mode=mode)
	else:
		info = "\n".join(info_list + info_list2)
		context.bot.scancelMessage(chat_id=os.environ.get("DEV_ID"),\
								text=info, parse_mode=mode)


def main() -> None:
	"봇을 시작"
	updater = Updater(token=os.environ.get("TOKEN"))
	dp = updater.dispatcher

	# 대화 : 기능, 이름, 검색, 작업, 복귀
	conv_handler = ConversationHandler(
		entry_points = [CommandHandler("start", start)],
		states = {
			SRT: [
				CallbackQueryHandler(cb_alert, pattern="^알림$"),
				CallbackQueryHandler(cb_help, pattern="^안내$"),
				CallbackQueryHandler(cb_cancel, pattern="^닫기$"),
			],
			WRK: [
				MessageHandler(Filters.text, cb_wrk),
			],
			SEL: [
				CallbackQueryHandler(cb_sel, pattern="^%d$"),
			],
			JOB: [
				CallbackQueryHandler(cb_new, pattern="^신작$"),
				CallbackQueryHandler(cb_ep, pattern="^차회$"),
			],
			CMP: [
				CallbackQueryHandler(start_over, pattern="^시작$"),
				CallbackQueryHandler(cb_cancel, pattern="^닫기$"),
			],
		},
		fallbacks = [CommandHandler("start", start)],
		per_message = True,
	)

	# 명령어
	dp.add_handler(CommandHandler("start", start))	# 시작
	dp.add_handler(CommandHandler("help", helps))	# 도움
	# dp.add_handler(CommandHandler("new", new))	# 신작
	# dp.add_handler(CommandHandler("ep", ep))		# 차회
	# dp.add_handler(CommandHandler("qna", qna))	# 문답

	# 오류 처리
	dp.add_handler(MessageHandler(Filters.command, unknown))
	dp.add_error_handler(error_handler)

	# 대화
	dp.add_handler(echo_handler)
	dp.add_handler(conv_handler)

	# 봇 시작
	updater.start_polling()

	# Ctrl-C 입력 및 SIGINT, SIGTERM, SIGABRT 신호를 받을 때까지 가동.
	updater.idle()


if __name__ == "__main__": main()
