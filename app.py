from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory, abort, Response
from datetime import datetime
import os, requests, csv, io, re, time
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from forms import ContactForm

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.secret_key = os.environ.get('SECRET_KEY', 'retec-dev-key-2026')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///portfolio.db')
if _db_url and _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', '')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('1', 'true', 'yes', 'on')
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() in ('1', 'true', 'yes', 'on')
app.config['MAIL_FROM'] = os.environ.get('MAIL_FROM', app.config['MAIL_USERNAME'])
app.config['MAIL_TO'] = os.environ.get('MAIL_TO', 'hello@retec.dev')
app.config['BREVO_API_KEY'] = os.environ.get('BREVO_API_KEY', '')
app.config['BREVO_LIST_ID'] = os.environ.get('BREVO_LIST_ID', '')
app.config['ZEROBOUNCE_API_KEY'] = os.environ.get('ZEROBOUNCE_API_KEY', '')
app.config['WTF_CSRF_TIME_LIMIT'] = 3600

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=['200 per day', '50 per hour'])

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

# ===== MODELS =====

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    category = db.Column(db.String(100), default='')
    tags = db.Column(db.String(500), default='')
    image_filename = db.Column(db.String(200), default='')
    github_url = db.Column(db.String(500), default='')
    featured = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()] or ['N/A']

class PageView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.String(200), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Interest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(100))
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LocationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    country = db.Column(db.String(100), default='')
    city = db.Column(db.String(100), default='')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class FunFact(db.Model):

class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(200), default='')
    text = db.Column(db.Text, nullable=False)
    avatar_filename = db.Column(db.String(200), default='')
    active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.String(500), default='')
    image_filename = db.Column(db.String(200), default='')
    published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

DISPOSABLE_DOMAINS = {
    'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'temp-mail.org',
    'throwaway.com', 'yopmail.com', 'sharklasers.com', '10minutemail.com',
    'trashmail.com', 'maildrop.cc', 'getairmail.com', 'emailondeck.com',
    'dispostable.com', 'mailnesia.com', 'mintemail.com', 'spambox.us',
    'tempmail.net', 'fakeinbox.com', 'throwaway.email', 'mailcatch.com',
    'mailexpire.com', 'tempinbox.com', 'spamgourmet.com', 'mytrashmail.com',
    'thankyou2010.com', 'trash2009.com', 'trashymail.com', 'tyldd.com',
    'uggsrock.com', 'wegwerfmail.de', 'wegwerfmail.net', 'wegwerfmail.org',
    'wh4f.org', 'whyspam.me', 'willselfdestruct.com', 'winemaven.info',
    'wronghead.com', 'wuzup.net', 'xagloo.com', 'xemaps.com',
    'xents.com', 'xmaily.com', 'xoxy.net', 'yep.it', 'yogamaven.com',
    'yopmail.fr', 'yopmail.net', 'ypmail.webarnak.com', 'yuurok.com',
    'zehnminutenmail.de', 'zippymail.info', 'zoaxe.com', 'zoemail.org',
    'spam4.me', 'filzmail.com', 'mailmetrash.com', 'rcpt.at',
    'trashinbox.net', 'spam.la', 'spam.cr', 'spam.od.ua',
    '0-mail.com', '0wnd.net', '0wnd.org', '1-8.biz', '1ce.us',
    '1chuy.com', '1mail.ml', '1pad.de', '1st-forms.com',
    '2ch.com.au', '2prong.com', '3d-painting.com', '4mail.cf',
    '4warding.com', '4warding.net', '4warding.org', '5mail.cf',
    '5ymail.com', '6qoz.com', '6paq.com', '7pcc.com',
    '7tags.com', '9mail.cf', 'a-bc.net', 'afrobacon.com',
    'amelijk.com', 'anonymail.dk', 'anonymbox.com', 'antichef.com',
    'antireg.com', 'antispam24.de', 'apinmail.com', 'armyspy.com',
    'autowb.com', 'azmeil.com', 'baxomale.ht.cx', 'beddly.com',
    'bigprofessor.so', 'bigstring.com', 'binkmail.com', 'bio-muesli.net',
    'bobmail.info', 'bombderfull.com', 'brennendesreich.de', 'broadbandninja.com',
    'bsnow.net', 'buffemail.com', 'buymoreplays.com', 'byebyemail.com',
    'card.zapto.org', 'casualdx.com', 'chacuo.net', 'choicemail1.com',
    'clixser.com', 'cmail.com', 'cool.fr.nf', 'correo.blogos.net',
    'cosmorph.com', 'courriel.fr.nf', 'courrieltemporaire.com', 'crapmail.org',
    'cubiclink.com', 'curryworld.de', 'cust.in', 'dacoolest.com',
    'dandikmail.com', 'dayrep.com', 'deadaddress.com', 'deadspam.com',
    'delikkt.de', 'despam.it', 'devnullmail.com', 'digitalsanctuary.com',
    'discard.email', 'discardmail.com', 'discardmail.de', 'dispose.it',
    'disposeamail.com', 'disposemail.com', 'dm.w3internet.co.uk',
    'dodgeit.com', 'dodgit.com', 'dodgit.org', 'donemail.ru',
    'dontreg.com', 'dontsendmespam.de', 'drdrb.com', 'dump-email.info',
    'dumpedmail.com', 'dumpmail.de', 'dumpyemail.com', 'e-mail.com',
    'e-mail.org', 'e4ward.com', 'easytrashmail.com', 'elitemail.org',
    'email-fake.com', 'email.cbes.net', 'email.net', 'emailgo.de',
    'emailias.com', 'emailigo.de', 'emailinfive.com', 'emailisvalid.com',
    'emaillime.com', 'emailmenow.de', 'emailmiser.com', 'emailna.co',
    'emails.ga', 'emails.tf', 'emailsensei.com', 'emailtech.info',
    'emailtemporanea.com', 'emailtemporanea.net', 'emailtemporar.ro',
    'emailtemps.com', 'ephemeral.email', 'etranquil.com', 'etranquil.net',
    'etranquil.org', 'exdonuts.com', 'explodemail.com', 'fake-email.com',
    'fakeinbox.info', 'fakeinformation.com', 'fakemail.fr', 'fakemailgenerator.com',
    'fakemailz.com', 'fammix.com', 'fansworldwide.de', 'fantasymail.de',
    'fdfdsfds.com', 'fightallspam.com', 'fivemail.de', 'fixmail.tk',
    'fizmail.com', 'flurred.com', 'forgetmail.com', 'freakmail.de',
    'free-email.ga', 'freebabysittercam.com', 'freemail.ms', 'freemail.tweakly.net',
    'freemails.cf', 'freemails.ga', 'friendlymail.co.uk', 'fuckingduh.com',
    'fudgerub.com', 'funnymail.de', 'gafy.net', 'garliclife.com',
    'gehensiemirnichtaufdensack.de', 'gelitik.in', 'get1mail.com', 'get2mail.fr',
    'getonemail.com', 'getonemail.net', 'ghosttexter.de', 'girlsindetention.com',
    'gitmail.ooo', 'goemailgo.com', 'gotmail.com', 'gotmail.org',
    'gotti.mobi', 'grr.la', 'gsrv.co.uk', 'guerrillamail.biz',
    'guerrillamail.net', 'guerrillamail.org', 'h7mail.com', 'haltospam.com',
    'hatespam.org', 'hiddencorner.xyz', 'hiddentragedy.com', 'hidemail.de',
    'hidemail.pro', 'hix.kr', 'hmail.us', 'hochsitze.com',
    'hotpop.com', 'hulapla.de', 'ieatspam.eu', 'ieatspam.info',
    'ignoremail.com', 'ihateyoualot.info', 'ik7gz5.com', 'imails.info',
    'inbax.tk', 'inbox.si', 'inboxalias.com', 'inboxbear.com',
    'inboxclean.com', 'inboxclean.org', 'inboxed.pw', 'inboxproxy.com',
    'incognitomail.com', 'incognitomail.net', 'incognitomail.org',
    'insorg-mail.info', 'ip6.li', 'irish2me.com', 'iwi.net',
    'jamieq.com', 'jet-renovation.fr', 'jkalucka.com', 'jourrapide.com',
    'jsrsolutions.com', 'kaitang.com', 'kasmail.com', 'kaspop.com',
    'killmail.com', 'killmail.net', 'kingsq.ga', 'kir.ch.tc',
    'klassmaster.com', 'klassmaster.net', 'kloap.com', 'knolpower.com',
    'kulturbetrieb.info', 'kurzepost.de', 'l33r.eu', 'laafd.com',
    'lackmail.net', 'lackmail.ru', 'lags.us', 'landmail.co',
    'lastmail.co', 'legitmail.club', 'letmymail.com', 'letterboxes.org',
    'linuxmail.so', 'litedrop.com', 'lobbyist.com', 'locatowa.com',
    'lol.com', 'lolfreak.net', 'lolmail.biz', 'lookugly.com',
    'lopl.co.cc', 'loremipsummail.com', 'lotsmail.biz', 'lovescomputers.com',
    'lr7.us', 'lroid.com', 'lukecarriere.com', 'm4ilweb.info',
    'maboard.com', 'mail.by', 'mail.mezimages.net', 'mail.om',
    'mail.wtf', 'mail0.ga', 'mail1.ga', 'mail114.net',
    'mail2.ga', 'mail2rss.org', 'mail333.com', 'mail4.ga',
    'mail4trash.com', 'mail666.ru', 'mail707.com', 'mailas.com',
    'mailbidon.com', 'mailbiz.biz', 'mailbucket.org', 'mailcat.biz',
    'mailde.de', 'mailde.info', 'maildrop.biz', 'maildrop.gq',
    'maildu.de', 'maildx.com', 'maileater.com', 'mailed.in',
    'mailed.ro', 'maileme101.com', 'mailexpire.com', 'mailf5.com',
    'mailfa.tk', 'mailforspam.com', 'mailfree.ga', 'mailfree.gq',
    'mailfree.ml', 'mailfs.com', 'mailguard.me', 'mailgutter.com',
    'mailhang.com', 'mailhazard.com', 'mailhazard.us', 'mailhex.com',
    'mailimate.com', 'mailin8r.com', 'mailinater.com', 'mailinator.co.uk',
    'mailinator.net', 'mailinator.org', 'mailinator2.com', 'mailinbox.co',
    'mailincubator.com', 'mailismagic.com', 'mailjunk.org', 'mailmate.com',
    'mailme.ga', 'mailme.gq', 'mailmenot.de', 'mailmetrash.com',
    'mailmoat.com', 'mailms.com', 'mailnator.com', 'mailnull.com',
    'mailpickup.com', 'mailpooch.com', 'mailproxsy.com', 'mailquack.com',
    'mailrc.biz', 'mailrock.biz', 'mailsac.com', 'mailscrap.com',
    'mailseal.de', 'mailshiv.com', 'mailslap.ga', 'mailsmachine.com',
    'mailspam.xyz', 'mailtemp.info', 'mailtome.de', 'mailtothis.com',
    'mailtrash.net', 'mailtrix.net', 'mailtv.net', 'mailtv.tv',
    'mailzi.com', 'mailzilla.com', 'mailzilla.org', 'makemetheking.com',
    'manybrain.com', 'mbx.cc', 'mciek.com', 'mega.zik.dj',
    'meinspamschutz.de', 'messagebeamer.de', 'messwiththebestdielikethe.rest',
    'mhmm.xyz', 'midcoastcustoms.com', 'midcoastcustoms.net', 'midlertidig.com',
    'midlertidig.net', 'midlertidig.org', 'mierdamail.com', 'mighty.co.za',
    'migmail.net', 'migmail.pl', 'migumail.com', 'mildin.org.ua',
    'mindless.com', 'mintemail.com', 'misterpinball.com', 'mmlki.be',
    'moakt.com', 'moakt.ws', 'mobilemail.ga', 'mobileninja.co.uk',
    'moncourrier.fr.nf', 'monemail.fr.nf', 'monmail.fr.nf', 'monumentmail.com',
    'moonwake.com', 'mountainregionallibrary.net', 'mrdrain.com', 'msgos.com',
    'muellemail.com', 'muell.icu', 'muellmail.com', 'mundodigital.net',
    'mwarner.org', 'my.bimi.ne', 'my.opendesktop.org', 'my10minutemail.com',
    'mycard.net.ua', 'mycleaninbox.net', 'mycorneroftheinter.net', 'mydeadaddress.com',
    'myemailboxy.com', 'myfavemail.com', 'myinterserver.ml', 'mymail-in.net',
    'mymail90.com', 'mymailoasis.com', 'mynetstore.de', 'myopang.com',
    'mypacks.net', 'mypartyclip.de', 'mytrashmail.com', 'mywarnet.net',
    'nabuma.com', 'neomailbox.com', 'nepwk.com', 'nervmich.net',
    'nervtmich.net', 'net.bitcoin.ph', 'netmails.com', 'netmails.net',
    'nevermail.de', 'nforget.com', 'nice-ix.com', 'nincsmail.com',
    'nincsmail.hu', 'nnh.com', 'nnot.net', 'no-spam.ws',
    'nobulk.com', 'noclickemail.com', 'nogmailspam.info', 'nomail.cf',
    'nomail.ga', 'nomail.pw', 'nomail.xl.cx', 'nomail2me.com',
    'nomorespamemails.com', 'nonspam.eu', 'nonspammer.de', 'noref.fr',
    'nothingtoseehere.ca', 'nowhere.org', 'nowmymail.com', 'ntlhelp.net',
    'nwldx.com', 'objectmail.com', 'obobbo.com', 'odnorazovoe.ru',
    'oemail.de', 'oida.icu', 'oil.gov.my', 'oiizz.com',
    'ok-bodycare.info', 'okmoney.net', 'oldiesmann.com', 'oneironaut.com',
    'onkwerks.com', 'online.ms', 'onmail.ws', 'onquebec.com',
    'oneuk.com', 'opayq.com', 'opp24.de', 'ordinaryamerican.net',
    'otherinbox.com', 'outlawspam.com', 'oxfarm1.com', 'ozyl.de',
    'pa9e.com', 'pancakemail.com', 'paplease.com', 'pcusers.otherinbox.com',
    'penisgoes.in', 'petrzilka.net', 'pfui.ru', 'pinknboobies.com',
    'pjqcn.com', 'plexolan.de', 'poczta.onet.pl', 'politikerclub.de',
    'poqbox.com', 'politikerclub.de', 'pookmail.com', 'poopiebutt.club',
    'popesodomy.com', 'popgx.com', 'postonline.cc', 'poutine.autresmouettes.net',
    'predatorrat.cf', 'prin.be', 'privacy.net', 'privy-mail.de',
    'privymail.de', 'proxymail.eu', 'prtnx.com', 'prtz.eu',
    'punkass.com', 'putthisinyourspamdatabase.com', 'pwp.lv', 'qiaua.com',
    'qisdo.com', 'qisoa.com', 'quickinbox.com', 'quickmail.nl',
    'ququb.com', 'qvy.me', 'r0.xxx', 'r3t.xxx',
    'raakkes.com', 'radiku.ye.vc', 'rancidhome.net', 'rbb.org',
    'rcpt.at', 'reality-concept.club', 'reallymymail.com', 'receiveee.com',
    'recipeforfailure.com', 'reconmail.com', 'recyclemail.dk', 'redditmail.com',
    'regbypass.com', 'regspaces.tk', 'rejectmail.com', 'remail.cf',
    'remail.ga', 'renmail.com', 'rengmail.com', 'resistore.net',
    'rhyta.com', 'rklips.com', 'rm2rf.com', 'rppkn.com',
    'rq1.in', 'ruggedinbox.com', 's0ny.net', 'safe-mail.net',
    'safersignup.com', 'safetymail.info', 'safetypost.de', 'sandelf.de',
    'sanstr.com', 'saynotospams.com', 'scattermail.com', 'schafmail.de',
    'schrott-email.de', 'secretemail.de', 'securehost.com.es', 'selfdestructingmail.com',
    'selfdestructingmail.org', 'sendfree.org', 'sendingspecialflyers.com', 'sendspamhere.com',
    'senseless-entertainment.com', 'server.ms', 'sexmagnet.com', 'shhmail.com',
    'shhuut.org', 'shieldedmail.com', 'shipfromto.com', 'shiphazmat.org',
    'shippingterms.org', 'shortmail.net', 'shotmail.ru', 'showslow.de',
    'sibmail.com', 'sinnlos-mail.de', 'siteposter.net', 'skarminko.com',
    'skeefmail.com', 'slaskmail.se', 'slipry.net', 'sly.io',
    'smap.4next.net', 'smapfree24.com', 'smapfree24.de', 'smapfree24.eu',
    'smapfree24.info', 'smapfree24.org', 'smapxsmap.net', 'smashmail.de',
    'smellfear.com', 'smellrear.com', 'snakemail.com', 'snapwet.com',
    'sneakemail.com', 'sneakerbunko.com', 'snkmail.com', 'snowdayonline.ca',
    'sofimail.com', 'solar-impact.pro', 'solvemail.info', 'songjoy.net',
    'soniamail.com', 'spam.2012-2016.ru', 'spam.la', 'spam.su',
    'spam4.me', 'spamail.de', 'spamarrest.com', 'spamavert.com',
    'spambob.com', 'spambob.net', 'spambob.org', 'spambog.com',
    'spambog.de', 'spambog.net', 'spambog.ru', 'spambox.info',
    'spambox.me', 'spambox.org', 'spambox.us', 'spamcannon.com',
    'spamcannon.net', 'spamcero.com', 'spamcon.org', 'spamcorptastic.com',
    'spamcowboy.com', 'spamcowboy.net', 'spamcowboy.org', 'spamday.com',
    'spamdecoy.net', 'spamex.com', 'spamfree24.com', 'spamfree24.de',
    'spamfree24.eu', 'spamfree24.info', 'spamfree24.net', 'spamfree24.org',
    'spamgoes.in', 'spamgourmet.com', 'spamgourmet.net', 'spamgourmet.org',
    'spamherelots.com', 'spamhereplease.com', 'spamhole.com', 'spamify.com',
    'spaminator.de', 'spamkill.info', 'spaml.com', 'spamlot.net',
    'spammotel.com', 'spamobox.com', 'spamoff.de', 'spamsalad.in',
    'spamserver.de', 'spamslicer.com', 'spamspame.com', 'spamspot.com',
    'spamstack.net', 'spamthis.co.uk', 'spamthisplease.com', 'spamtrail.com',
    'spamtroll.net', 'speed.1s.fr', 'spoofmail.de', 'squizzy.com',
    'ssoia.com', 'startfu.com', 'steambot.net', 'stexsy.com',
    'stinkysugar.net', 'suburbanthug.com', 'suckmyd.com', 'sudolife.me',
    'suioe.com', 'supergreatmail.com', 'supermailer.jp', 'superplatyna.com',
    'superrito.com', 'superstachel.de', 'surfmail.tk', 'susi.ml',
    'svxr.org', 'sweetxxx.de', 'tafmail.com', 'taginvolve.com',
    'talkmises.com', 'tanukis.org', 'tapchicuoihoi.com', 'tarzanmail.cf',
    'techemail.com', 'techgroup.me', 'teleosaurs.xyz', 'teewars.org',
    'temp-mail.com', 'temp-mail.de', 'temp-mail.org', 'temp.e mail',
    'temp.emeraldwebmail.com', 'temp.headstrong.de', 'tempail.com',
    'tempalias.com', 'tempe-mail.com', 'tempemail.biz', 'tempemail.co.za',
    'tempemail.co', 'tempemail.com', 'tempemail.net', 'tempemail.org',
    'tempinbox.co.za', 'tempinbox.com', 'tempmail.co', 'tempmail.it',
    'tempmail4you.com', 'tempmaildemo.com', 'tempmailer.com', 'tempmailer.de',
    'tempomail.fr', 'temporarily.de', 'temporarioemail.com.br', 'temporaryemail.net',
    'temporaryemail.us', 'temporaryforwarding.com', 'temporaryinbox.com',
    'temporarymail.org', 'tempthe.net', 'tempymail.com', 'ternak.com',
    'testisite.org', 'thankyou2010.com', 'theaviors.com', 'thebearshark.com',
    'thelightningmail.com', 'thembones.com.au', 'themostemail.com', 'thediamants.com',
    'thescrapp.us', 'theteastory.com', 'thraml.com', 'throwamail.com',
    'throwaway.email', 'throwaway.xyz', 'throwawayemail.com', 'throya.com',
    'thrubay.com', 'tittibit.net', 'tizi.com', 'tmail.com',
    'tmail.ws', 'tmailinator.com', 'toiea.com', 'toitag.com',
    'tokem.co', 'tonymanso.com', 'toomail.biz', 'top101.de',
    'topaddress.net', 'topranklist.de', 'tormail.net', 'tormail.org',
    'tradermail.info', 'trash-amil.com', 'trash-me.com', 'trash2009.com',
    'trash2010.com', 'trash2011.com', 'trashdevil.com', 'trashemail.de',
    'trashemails.de', 'trashinbox.com', 'trashmail.at', 'trashmail.com',
    'trashmail.de', 'trashmail.me', 'trashmail.net', 'trashmail.org',
    'trashmail.ws', 'trashmailer.com', 'trashmails.com', 'trashspam.com',
    'trashymail.net', 'trbvm.com', 'trialmail.de', 'trillianpro.com',
    'tryalert.com', 'turoid.com', 'turual.com', 'tvchd.com',
    'twkly.ml', 'two.pw', 'ty.ceed.se', 'tyldd.com',
    'uacro.com', 'uber-mail.com', 'uggsrock.com', 'uk.to',
    'umail.net', 'undo.it', 'unimark.org', 'unit7lahaina.com',
    'upliftnow.com', 'uplipht.com', 'upozowas.info', 'urfunny.net',
    'uroid.com', 'us.af', 'ux.dob.jp', 'uyhip.com',
    'valemail.net', 'veanlo.com', 'venompen.com', 'vgtmail.com',
    'vipmail.name', 'vipmail.pw', 'vixletdev.com', 'vjtimail.com',
    'vmailing.info', 'vmani.com', 'vnedu.me', 'voidbay.com',
    'vomoto.com', 'vsimcard.com', 'vubby.com', 'vzw.com',
    'w3internet.co.uk', 'wakingupesther.com', 'walala.org', 'walkmail.net',
    'walkmail.ru', 'wasteland.rfc822.org', 'watchandiron.com', 'webm4il.info',
    'webmail.xyz', 'webuser.in', 'wee.my', 'wefjo.grn.cc',
    'wegwerfmail.de', 'wegwerfmail.net', 'wegwerfmail.org', 'wetrainbayarea.com',
    'wetrainbayarea.org', 'wh4f.org', 'whatiaas.com', 'whatpaas.com',
    'whitemail.org', 'whoever.com', 'wifflemail.com', 'wimsemail.com',
    'winemaven.info', 'wins.com.br', 'wlist.e', 'wmik.ro',
    'wmsnorris.com', 'wokcy.com', 'woodlandsummer.com', 'wopr.com',
    'workmail24.com', 'wovz.cf', 'wralawfirm.com', 'wronghead.com',
    'wuzup.net', 'xagloo.com', 'xemaps.com', 'xents.com',
    'xmail.com', 'xmaily.com', 'xoxy.net', 'xweb.dk',
    'xww.ro', 'yabai-oppai.org', 'yahmail.top', 'yamha.info',
    'yapped.net', 'yarnpedia.net', 'yep.it', 'yopmail.com',
    'yopmail.fr', 'yopmail.net', 'yopmail.org', 'youmail.ga',
    'youmailr.com', 'youneedmore.info', 'yourdomain.com', 'yourewronghereswhy.com',
    'yoursuccessfulincome.com', 'yourtrap.com', 'youzoko.net', 'ypmail.webarnak.com',
    'yuurok.com', 'z0d.eu', 'z1p.biz', 'za.com',
    'zain.site', 'zainmax.net', 'zarabotai.site', 'zehnminutenmail.de',
    'zehnminutenmail.net', 'zep-hyr.com', 'zhcne.com', 'zhorachu.com',
    'zipcad.com', 'zippymail.info', 'zoaxe.com', 'zoemail.org',
    'zomg.info', 'zonedetravail.com', 'zsero.com', 'zumpat.com',
    'zxcv.com', 'zxcvbnm.com', 'zzz.com'
}

class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(100), default='')
    source = db.Column(db.String(100), default='website')
    brevo_synced = db.Column(db.Boolean, default=False)
    validated = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ===== HELPERS =====

_geo_cache = {}

def lookup_location(ip):
    if not ip or ip in ('127.0.0.1', '::1', 'localhost'):
        return None
    if ip in _geo_cache:
        return _geo_cache[ip]
    try:
        r = requests.get(f'http://ip-api.com/json/{ip}?fields=country,city,query', timeout=3)
        if r.status_code == 200:
            data = r.json()
            if data.get('country'):
                result = {'country': data['country'], 'city': data.get('city', '')}
                _geo_cache[ip] = result
                return result
    except Exception:
        pass
    _geo_cache[ip] = None
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def get_github_projects():
    try:
        r = requests.get('https://api.github.com/users/echoesrule/repos?sort=updated&per_page=20', timeout=5)
        if r.status_code != 200:
            return []
        repos = r.json()
        if not isinstance(repos, list):
            return []
        projects = []
        for repo in repos:
            if repo.get('fork'):
                continue
            tags = []
            if repo.get('language'):
                tags.append(repo['language'])
            tags.extend(repo.get('topics', [])[:4])
            projects.append({
                'title': repo['name'].replace('-', ' ').replace('_', ' ').title(),
                'description': repo.get('description') or 'No description provided.',
                'tags': tags or ['N/A'],
                'github': repo['html_url'],
                'image': repo['owner']['avatar_url']
            })
        return projects[:6]
    except Exception:
        return []

def get_projects(category=None):
    q = Project.query.order_by(Project.sort_order, Project.created_at.desc())
    if category:
        q = q.filter_by(category=category)
    db_projects = q.all()
    if db_projects:
        return [{
            'title': p.title,
            'description': p.description or 'No description provided.',
            'tags': p.tag_list(),
            'github': p.github_url or '#',
            'image': url_for('static', filename='uploads/' + p.image_filename) if p.image_filename else '',
            'id': p.id,
            'category': p.category
        } for p in db_projects]
    return get_github_projects()

def get_github_stats():
    try:
        r = requests.get('https://api.github.com/users/echoesrule', timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        return {'public_repos': data.get('public_repos', 0), 'followers': data.get('followers', 0)}
    except Exception:
        return None

def send_email(name, email, subject, message, ip_address=''):
    if not app.config['MAIL_SERVER'] or not app.config['MAIL_FROM'] or not app.config['MAIL_TO']:
        app.logger.warning('Contact email skipped: SMTP settings are incomplete.')
        return False
    try:
        import smtplib
        from email.message import EmailMessage

        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        body = (
            f"New portfolio contact message\n\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Subject: {subject}\n"
            f"IP: {ip_address}\n"
            f"Time: {timestamp}\n\n"
            f"Message:\n{message}"
        )
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = f"Portfolio Contact: {subject[:80]}"
        msg['From'] = app.config['MAIL_FROM']
        msg['To'] = app.config['MAIL_TO']
        msg['Reply-To'] = email

        smtp_class = smtplib.SMTP_SSL if app.config['MAIL_USE_SSL'] else smtplib.SMTP
        with smtp_class(app.config['MAIL_SERVER'], app.config['MAIL_PORT'], timeout=20) as server:
            if app.config['MAIL_USE_TLS'] and not app.config['MAIL_USE_SSL']:
                server.starttls()
            if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            server.send_message(msg)
        return True
    except Exception as exc:
        app.logger.exception('Contact email failed: %s', exc)
        return False

RETEC_EMAIL_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body { margin:0; padding:0; background:#f5f5f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif; }
  .wrapper { max-width:600px; margin:0 auto; padding:24px 16px; }
  .header { text-align:center; padding:32px 0 8px; }
  .header .logo-box { display:inline-block; border:2px solid #000; border-radius:8px; padding:0; width:56px; height:56px; position:relative; }
  .header .logo-box .r-mark { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); width:32px; height:32px; }
  .header .logo-box .r-mark span { display:block; font-size:28px; font-weight:700; line-height:1; color:#000; text-align:center; }
  .header h1 { font-size:22px; font-weight:700; letter-spacing:3px; text-transform:uppercase; color:#000; margin:10px 0 0; }
  .header p { font-size:11px; color:#999; letter-spacing:2px; text-transform:uppercase; margin:4px 0 0; }
  .body { background:#fff; border:1px solid #e0e0e0; padding:32px; color:#1a1a1a; font-size:15px; line-height:1.7; }
  .body a { color:#000; text-decoration:underline; }
  .footer { text-align:center; padding:24px 0 8px; font-size:12px; color:#999; }
  .footer a { color:#999; text-decoration:underline; }
  .social-links { margin:16px 0; }
  .social-links a { display:inline-block; margin:0 6px; text-decoration:none; }
  .social-links img { width:20px; height:20px; display:block; border:none; }
  hr { border:none; border-top:1px solid #eee; margin:24px 0; }
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA1MDAgMTIwIiBmaWxsPSJub25lIj4KICA8ZyB0cmFuc2Zvcm09InRyYW5zbGF0ZSg0MCwgMjgpIj4KICAgIDxsaW5lIHgxPSIwIiB5MT0iMTIiIHgyPSI0MCIgeTI9IjEyIiBzdHJva2U9IiMwMDAiIHN0cm9rZS13aWR0aD0iNCIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+CiAgICA8bGluZSB4MT0iMjAiIHkxPSIxMiIgeDI9IjIwIiB5Mj0iNDgiIHN0cm9rZT0iIzAwMCIgc3Ryb2tlLXdpZHRoPSI0IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KICAgIDxwYXRoIGQ9Ik0gMjAgMTYgQSAxMiAxMiAwIDAgMSAyMCA0MCIgc3Ryb2tlPSIjMDAwIiBzdHJva2Utd2lkdGg9IjQiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgogICAgPHBhdGggZD0iTSAzMCAzNiBMIDQwIDQ4IiBzdHJva2U9IiMwMDAiIHN0cm9rZS13aWR0aD0iNCIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+CiAgPC9nPgogIDx0ZXh0IHg9IjEwMCIgeT0iNzIiIGZvbnQtZmFtaWx5PSInSW50ZXInLCAnSGVsdmV0aWNhIE5ldWUnLCBBcmlhbCwgc2Fucy1zZXJpZiIgZm9udC1zaXplPSI1MiIgZm9udC13ZWlnaHQ9IjcwMCIgbGV0dGVyLXNwYWNpbmc9IjEyIiBmaWxsPSIjMDAwIj5SRVRFQzwvdGV4dD4KICA8bGluZSB4MT0iMTAwIiB5MT0iODgiIHgyPSI0MzYiIHkyPSI4OCIgc3Ryb2tlPSIjMDAwIiBzdHJva2Utd2lkdGg9IjEuNSIvPgogIDxyZWN0IHg9IjQ0MCIgeT0iODUuNSIgd2lkdGg9IjMiIGhlaWdodD0iMyIgZmlsbD0iIzAwMCIvPgo8L3N2Zz4=" alt="RETEC" width="320" height="auto" style="display:inline-block;border:none;max-width:100%;">
    <p style="font-size:11px;color:#999;letter-spacing:2px;text-transform:uppercase;margin:4px 0 0;">Retro Spirit &middot; Modern Solutions</p>
  </div>
  <div class="body">{{ content | safe }}</div>
  <hr>
  <div class="footer">
    <div class="social-links">
      <a href="https://github.com/echoesrule" target="_blank"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/github.svg" alt="GitHub" width="20" height="20"></a>
      <a href="https://www.linkedin.com/in/emmanuel-kiprono-14a800389" target="_blank"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/linkedin.svg" alt="LinkedIn" width="20" height="20"></a>
      <a href="https://wa.me/0114581500" target="_blank"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/whatsapp.svg" alt="WhatsApp" width="20" height="20"></a>
    </div>
    <p>You received this email because you subscribed on <a href="https://retec.dev">retec.dev</a>.</p>
    <p style="margin-top:4px"><a href="{{ unsubscribe_url }}">Unsubscribe</a></p>
  </div>
</div>
</body>
</html>"""

def send_broadcast(subject, html_content, test_email=None):
    if not app.config['MAIL_SERVER'] or not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return False, "SMTP not configured."

    import smtplib
    from email.message import EmailMessage

    unsub_placeholder = url_for('home', _external=True) + '#unsubscribe'

    targets = []
    if test_email:
        targets = [{'email': test_email, 'name': 'Test'}]
    else:
        targets = Subscriber.query.filter_by(active=True).all()
        if not targets:
            return False, "No active subscribers."

    sent = 0
    failed = 0
    for sub in targets:
        try:
            email = sub.email if hasattr(sub, 'email') else sub['email']
            name = (sub.name or '') if hasattr(sub, 'name') else sub.get('name', '')
            greeting = f"Hi {name or 'there'},"
            unsub = url_for('unsubscribe', email=email, _external=True)
            html = RETEC_EMAIL_TEMPLATE.replace('{{ content | safe }}', f"<p>{greeting}</p>{html_content}").replace('{{ unsubscribe_url }}', unsub)

            msg = EmailMessage()
            msg.set_content(f"View this email in a browser that supports HTML.\n\nSubject: {subject}")
            msg.add_alternative(html, subtype='html')
            msg['Subject'] = subject
            broadcast_from = app.config.get('MAIL_FROM', 'contact.retec@gmail.com')
            msg['From'] = f'RETEC <{broadcast_from}>'
            msg['To'] = email

            smtp_class = smtplib.SMTP_SSL if app.config['MAIL_USE_SSL'] else smtplib.SMTP
            with smtp_class(app.config['MAIL_SERVER'], app.config['MAIL_PORT'], timeout=20) as server:
                if app.config['MAIL_USE_TLS'] and not app.config['MAIL_USE_SSL']:
                    server.starttls()
                if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
                    server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.send_message(msg)
            sent += 1
        except Exception as exc:
            app.logger.exception('Broadcast email failed to %s: %s', email if 'email' in dir() else 'unknown', exc)
            failed += 1
    return True, f"Sent: {sent}, Failed: {failed}"

@app.route('/unsubscribe')
def unsubscribe():
    email = request.args.get('email', '').strip().lower()
    if email:
        sub = Subscriber.query.filter_by(email=email).first()
        if sub:
            sub.active = False
            db.session.commit()
            flash('You have been unsubscribed.', 'info')
    return redirect(url_for('home'))

@app.route('/admin/broadcast', methods=['GET', 'POST'])
@admin_required
@csrf.exempt
def admin_broadcast():
    result = None
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        content = request.form.get('content', '').strip()
        test = request.form.get('test_email', '').strip()
        if not subject or not content:
            flash('Subject and content are required.', 'error')
        else:
            ok, msg = send_broadcast(subject, content, test_email=test or None)
            if ok:
                flash(f'Broadcast sent. {msg}', 'success')
            else:
                flash(f'Failed: {msg}', 'error')
        return redirect(url_for('admin_broadcast'))
    subscriber_count = Subscriber.query.filter_by(active=True).count()
    return render_template('admin/broadcast.html', subscriber_count=subscriber_count)

def is_disposable_email(email):
    domain = (email or '').split('@')[-1].strip().lower()
    return domain in DISPOSABLE_DOMAINS

def check_mx_record(domain):
    try:
        import socket
        socket.getaddrinfo(domain, 25, socket.AF_INET, socket.SOCK_STREAM)
        return True
    except Exception:
        return False

BIG_PROVIDERS = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'aol.com', 'icloud.com', 'protonmail.com', 'mail.com'}

def smtp_verify(email, timeout=5):
    domain = email.split('@')[-1]
    if domain in BIG_PROVIDERS:
        return None
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX')
        mx_host = str(sorted(answers, key=lambda r: r.preference)[0].exchange).rstrip('.')
    except Exception:
        return None
    try:
        import smtplib
        sock = smtplib.SMTP(timeout=timeout)
        sock.connect(mx_host, 25)
        sock.ehlo_or_helo_if_needed()
        sock.mail('check@example.com')
        code, _ = sock.rcpt(email)
        sock.quit()
        return code == 250
    except Exception:
        return None

def verify_email_api(email):
    api_key = app.config['ZEROBOUNCE_API_KEY']
    if not api_key:
        return None
    try:
        resp = requests.get(
            'https://api.zerobounce.net/v2/validate',
            params={'api_key': api_key, 'email': email},
            timeout=10
        )
        data = resp.json()
        status = data.get('status', '')  # Valid, Invalid, Catch-All, Unknown, do_not_mail
        sub_status = data.get('sub_status', '')
        if status == 'Valid':
            return True
        if status == 'do_not_mail' and sub_status in ('role_based', 'disposable'):
            return False
        if status == 'Invalid':
            return False
        return None
    except Exception:
        return None

def is_valid_email(email):
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email or ''):
        return False
    if is_disposable_email(email):
        return False
    return True

def sync_brevo_contact(email, name=''):
    api_key = app.config['BREVO_API_KEY']
    list_id = app.config['BREVO_LIST_ID']
    if not api_key or not list_id:
        app.logger.info('Brevo sync skipped: BREVO_API_KEY or BREVO_LIST_ID is missing.')
        return False
    try:
        payload = {
            'email': email,
            'attributes': {'FIRSTNAME': name} if name else {},
            'listIds': [int(list_id)],
            'updateEnabled': True
        }
        response = requests.post(
            'https://api.brevo.com/v3/contacts',
            headers={
                'accept': 'application/json',
                'api-key': api_key,
                'content-type': 'application/json'
            },
            json=payload,
            timeout=15
        )
        if response.status_code in (200, 201, 204):
            return True
        app.logger.warning('Brevo sync failed with status %s: %s', response.status_code, response.text[:500])
    except Exception as exc:
        app.logger.exception('Brevo sync failed: %s', exc)
    return False

def save_subscriber(email, name='', source='website'):
    email = (email or '').strip().lower()
    name = (name or '').strip()
    if not is_valid_email(email):
        return None, False

    subscriber = Subscriber.query.filter_by(email=email).first()
    created = subscriber is None
    if created:
        subscriber = Subscriber(email=email, name=name, source=source)
        db.session.add(subscriber)
    else:
        if name and not subscriber.name:
            subscriber.name = name
        subscriber.active = True

    if not subscriber.validated:
        api_result = verify_email_api(email)
        if api_result is True:
            subscriber.validated = True
        elif api_result is None:
            smtp_result = smtp_verify(email)
            if smtp_result is True:
                subscriber.validated = True
            elif smtp_result is None:
                domain = email.split('@')[-1]
                if check_mx_record(domain):
                    subscriber.validated = True

    synced = sync_brevo_contact(email, name or subscriber.name)
    subscriber.brevo_synced = subscriber.brevo_synced or synced
    db.session.commit()
    return subscriber, created

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text

services = [
    'Website Development',
    'Portfolio Websites',
    'Web Applications',
    'Python Solutions',
    'Website Maintenance'
]

# ===== CONTEXT PROCESSORS =====

@app.context_processor
def inject_globals():
    fun_fact = FunFact.query.filter_by(active=True).order_by(FunFact.updated_at.desc()).first()
    github_stats = get_github_stats()
    try:
        meta_url = request.url
        meta_image = url_for('static', filename='uploads/default-og.png', _external=True)
    except RuntimeError:
        meta_url = '/'
        meta_image = ''
    return {
        'year': datetime.now().year,
        'css_version': int(datetime.now().timestamp()),
        'fun_fact': fun_fact.text if fun_fact else None,
        'github_stats': github_stats,
        'meta_title': 'RETEC — Retro Spirit. Modern Solutions.',
        'meta_desc': 'RETEC is a software developer building modern websites, web applications, and digital experiences.',
        'meta_url': meta_url,
        'meta_image': meta_image
    }

# ===== AFTER REQUEST =====

@app.after_request
def no_cache(response):
    if request.path.startswith('/static/'):
        return response
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.before_request
def track_pageview():
    if 'admin_id' in session:
        return
    if request.path.startswith('/static') or request.path.startswith('/track') or request.path.startswith('/admin') or request.path == '/favicon.ico':
        return
    ip = request.remote_addr
    view = PageView(
        page=request.path,
        ip_address=ip,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(view)
    db.session.commit()
    geo = lookup_location(ip)
    if geo:
        existing = LocationLog.query.filter_by(ip_address=ip).first()
        if not existing:
            db.session.add(LocationLog(ip_address=ip, country=geo['country'], city=geo['city']))
            db.session.commit()

# ===== ERROR HANDLERS =====

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(429)
def rate_limited(e):
    flash('Too many messages. Please try again later.', 'error')
    return redirect(url_for('home') + '#contact')

# ===== PUBLIC ROUTES =====

def get_homepage_data():
    return {
        'projects': get_projects(),
        'testimonials': Testimonial.query.filter_by(active=True).order_by(Testimonial.sort_order).all(),
        'blog_posts': BlogPost.query.filter_by(published=True).order_by(BlogPost.created_at.desc()).limit(3).all(),
        'services': services
    }

@app.route('/')
def home():
    return render_template('index.html', active='home', **get_homepage_data())

@app.route('/contact', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
@csrf.exempt
def contact():
    form = ContactForm()
    honeypot = request.form.get('website', '')
    if form.validate_on_submit() and not honeypot:
        ip = request.remote_addr or '0.0.0.0'
        if send_email(form.name.data, form.email.data, form.subject.data, form.message.data, ip):
            flash('Thank you for your message. I will get back to you soon.', 'success')
        else:
            flash('Your message could not be sent right now. Please email me directly.', 'error')
        save_subscriber(form.email.data, form.name.data, source='contact')
        return redirect(url_for('home') + '#contact')
    context = get_homepage_data()
    context['form'] = form
    context['active'] = 'home'
    return render_template('index.html', **context)

@app.route('/subscribe', methods=['POST'])
@csrf.exempt
def subscribe():
    honeypot = request.form.get('website', '')
    if honeypot:
        return redirect(url_for('home') + '#contact')
    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()
    if not email:
        flash('Please enter your email address.', 'error')
        return redirect(url_for('home') + '#contact')
    subscriber, created = save_subscriber(email, name, source='newsletter')
    if subscriber:
        if created:
            flash('Thanks for subscribing! Stay tuned for updates.', 'success')
        else:
            flash('You are already subscribed!', 'info')
    else:
        flash('That email address does not look valid.', 'error')
    return redirect(url_for('home') + '#contact')

@app.route('/verify-email', methods=['POST'])
@csrf.exempt
def verify_email():
    data = request.get_json(silent=True) or {}
    email = (data.get('email', '') or '').strip().lower()
    if not email:
        return jsonify({'valid': False, 'message': 'Enter an email address.'})
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'valid': False, 'message': 'Invalid email format.'})
    if is_disposable_email(email):
        return jsonify({'valid': False, 'message': 'Disposable email not allowed.'})
    api_result = verify_email_api(email)
    if api_result is True:
        return jsonify({'valid': True, 'message': 'Email verified.'})
    if api_result is False:
        return jsonify({'valid': False, 'message': 'Email does not appear to exist.'})
    smtp_result = smtp_verify(email)
    if smtp_result is True:
        return jsonify({'valid': True, 'message': 'Email exists.'})
    if smtp_result is False:
        return jsonify({'valid': False, 'message': 'Email does not appear to exist.'})
    domain = email.split('@')[-1]
    if check_mx_record(domain):
        return jsonify({'valid': True, 'message': 'Email looks good.'})
    return jsonify({'valid': False, 'message': 'Could not verify this email.'})

@app.route('/cv')
def cv():
    return render_template('cv.html', active='cv')

@app.route('/blog')
def blog():
    posts = BlogPost.query.filter_by(published=True).order_by(BlogPost.created_at.desc()).all()
    return render_template('blog.html', active='blog', posts=posts)

@app.route('/blog/<slug>')
def blog_post(slug):
    post = BlogPost.query.filter_by(slug=slug, published=True).first_or_404()
    return render_template('blog_post.html', post=post)

# ===== TRACKING ROUTES =====

@app.route('/track/pageview', methods=['POST'])
@csrf.exempt
def track_pageview_ajax():
    if 'admin_id' in session:
        return '', 204
    ip = request.remote_addr
    data = request.get_json(silent=True) or {}
    view = PageView(
        page=data.get('page', '/'),
        ip_address=ip,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(view)
    db.session.commit()
    geo = lookup_location(ip)
    if geo:
        existing = LocationLog.query.filter_by(ip_address=ip).first()
        if not existing:
            db.session.add(LocationLog(ip_address=ip, country=geo['country'], city=geo['city']))
            db.session.commit()
    return '', 204

@app.route('/track/interest', methods=['POST'])
@csrf.exempt
def track_interest():
    if 'admin_id' in session:
        return '', 204
    ip = request.remote_addr
    data = request.get_json(silent=True) or {}
    interest = Interest(
        section=data.get('section', 'unknown'),
        action=data.get('action', 'view'),
        ip_address=ip
    )
    db.session.add(interest)
    db.session.commit()
    geo = lookup_location(ip)
    if geo:
        existing = LocationLog.query.filter_by(ip_address=ip).first()
        if not existing:
            db.session.add(LocationLog(ip_address=ip, country=geo['country'], city=geo['city']))
            db.session.commit()
    return '', 204

# ===== ADMIN ROUTES =====

@app.route('/admin/login', methods=['GET', 'POST'])
@csrf.exempt
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            session['admin_id'] = user.id
            session['admin_username'] = user.username
            flash('Welcome back, admin.', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials.', 'error')
        return redirect(url_for('admin_login'))
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('Logged out.', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def admin_change_password():
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        user = db.session.get(User, session['admin_id'])
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('admin_logout'))
        if not bcrypt.check_password_hash(user.password_hash, current):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('admin_change_password'))
        if len(new) < 6:
            flash('New password must be at least 6 characters.', 'error')
            return redirect(url_for('admin_change_password'))
        if new != confirm:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('admin_change_password'))
        user.password_hash = bcrypt.generate_password_hash(new).decode('utf-8')
        db.session.commit()
        flash('Password changed successfully.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/change_password.html')

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_views = PageView.query.count()
    unique_visitors = db.session.query(PageView.ip_address).distinct().count()
    project_count = Project.query.count()
    testimonial_count = Testimonial.query.count()
    blog_count = BlogPost.query.count()
    top_pages = db.session.query(
        PageView.page, db.func.count(PageView.id).label('count')
    ).group_by(PageView.page).order_by(db.desc('count')).limit(10).all()
    recent_views = PageView.query.order_by(PageView.timestamp.desc()).limit(20).all()
    total_interests = Interest.query.count()
    top_sections = db.session.query(
        Interest.section, db.func.count(Interest.id).label('count')
    ).group_by(Interest.section).order_by(db.desc('count')).limit(10).all()
    subscriber_count = Subscriber.query.count()
    return render_template('admin/dashboard.html',
        total_views=total_views, unique_visitors=unique_visitors,
        project_count=project_count, testimonial_count=testimonial_count,
        blog_count=blog_count, top_pages=top_pages,
        recent_views=recent_views, total_interests=total_interests,
        top_sections=top_sections, subscriber_count=subscriber_count)

# ----- Projects -----

@app.route('/admin/projects')
@admin_required
def admin_projects():
    projects = Project.query.order_by(Project.sort_order, Project.created_at.desc()).all()
    github_repos = []
    try:
        r = requests.get('https://api.github.com/users/echoesrule/repos?sort=updated&per_page=30', timeout=5)
        if r.status_code == 200:
            for repo in r.json():
                if not repo.get('fork') and isinstance(repo, dict):
                    github_repos.append(repo)
    except Exception:
        pass
    return render_template('admin/projects.html', projects=projects, github_repos=github_repos)

@app.route('/admin/projects/add', methods=['GET', 'POST'])
@admin_required
def admin_project_add():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'error')
            return redirect(url_for('admin_project_add'))
        image_filename = ''
        if request.files.get('image'):
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename
        project = Project(
            title=title,
            description=request.form.get('description', ''),
            category=request.form.get('category', ''),
            tags=request.form.get('tags', ''),
            image_filename=image_filename,
            github_url=request.form.get('github_url', ''),
            featured=bool(request.form.get('featured')),
            sort_order=int(request.form.get('sort_order', 0))
        )
        db.session.add(project)
        db.session.commit()
        flash('Project added.', 'success')
        return redirect(url_for('admin_projects'))
    prefill = {
        'title': request.args.get('title', ''),
        'description': request.args.get('description', ''),
        'github_url': request.args.get('github_url', '')
    }
    return render_template('admin/project_form.html', project=None, prefill=prefill)

@app.route('/admin/projects/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_project_edit(id):
    project = Project.query.get_or_404(id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'error')
            return redirect(url_for('admin_project_edit', id=id))
        project.title = title
        project.description = request.form.get('description', '')
        project.category = request.form.get('category', '')
        project.tags = request.form.get('tags', '')
        project.github_url = request.form.get('github_url', '')
        project.featured = bool(request.form.get('featured'))
        project.sort_order = int(request.form.get('sort_order', 0))
        if request.files.get('image') and request.files['image'].filename:
            file = request.files['image']
            if allowed_file(file.filename):
                if project.image_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], project.image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                project.image_filename = filename
        db.session.commit()
        flash('Project updated.', 'success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/project_form.html', project=project, prefill={})

@app.route('/admin/projects/delete/<int:id>', methods=['POST'])
@admin_required
def admin_project_delete(id):
    project = Project.query.get_or_404(id)
    if project.image_filename:
        path = os.path.join(app.config['UPLOAD_FOLDER'], project.image_filename)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted.', 'success')
    return redirect(url_for('admin_projects'))

# ----- Analytics + CSV Export -----

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    return render_template('admin/analytics.html')

@app.route('/admin/api/analytics/summary')
@admin_required
def admin_analytics_summary():
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    total_views = PageView.query.count()
    unique_visitors = db.session.query(PageView.ip_address).distinct().count()
    total_interests = Interest.query.count()
    recent_views = PageView.query.filter(PageView.timestamp >= thirty_days_ago).count()
    return jsonify({
        'total_views': total_views,
        'unique_visitors': unique_visitors,
        'total_interests': total_interests,
        'recent_views': recent_views
    })

@app.route('/admin/api/analytics/views-over-time')
@admin_required
def admin_analytics_views_over_time():
    from datetime import datetime, timedelta
    import sqlalchemy as sa
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    rows = db.session.query(
        sa.func.date(PageView.timestamp).label('date'),
        sa.func.count(PageView.id).label('count')
    ).filter(PageView.timestamp >= thirty_days_ago
    ).group_by(sa.func.date(PageView.timestamp)
    ).order_by('date').all()
    labels = [(datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]
    counts = {str(r.date): r.count for r in rows}
    data = [counts.get(d, 0) for d in labels]
    return jsonify({'labels': labels, 'data': data})

@app.route('/admin/api/analytics/top-pages')
@admin_required
def admin_analytics_top_pages():
    import sqlalchemy as sa
    rows = db.session.query(
        PageView.page, sa.func.count(PageView.id).label('count')
    ).group_by(PageView.page).order_by(sa.desc('count')).limit(10).all()
    return jsonify({
        'labels': [r.page for r in rows],
        'data': [r.count for r in rows]
    })

@app.route('/admin/api/analytics/section-interests')
@admin_required
def admin_analytics_section_interests():
    import sqlalchemy as sa
    rows = db.session.query(
        Interest.section, sa.func.count(Interest.id).label('count')
    ).group_by(Interest.section).order_by(sa.desc('count')).all()
    return jsonify({
        'labels': [r.section for r in rows],
        'data': [r.count for r in rows]
    })

@app.route('/admin/api/analytics/interests-over-time')
@admin_required
def admin_analytics_interests_over_time():
    from datetime import datetime, timedelta
    import sqlalchemy as sa
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    rows = db.session.query(
        sa.func.date(Interest.timestamp).label('date'),
        sa.func.count(Interest.id).label('count')
    ).filter(Interest.timestamp >= thirty_days_ago
    ).group_by(sa.func.date(Interest.timestamp)
    ).order_by('date').all()
    labels = [(datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]
    counts = {str(r.date): r.count for r in rows}
    data = [counts.get(d, 0) for d in labels]
    return jsonify({'labels': labels, 'data': data})

@app.route('/admin/api/analytics/locations')
@admin_required
def admin_analytics_locations():
    import sqlalchemy as sa
    rows = db.session.query(
        LocationLog.country, sa.func.count(LocationLog.id).label('count')
    ).group_by(LocationLog.country).order_by(sa.desc('count')).all()
    total = sum(r.count for r in rows)
    return jsonify({
        'labels': [r.country for r in rows],
        'data': [r.count for r in rows],
        'total': total
    })

@app.route('/admin/analytics/clear', methods=['POST'])
@admin_required
def admin_analytics_clear():
    try:
        PageView.query.delete()
        Interest.query.delete()
        LocationLog.query.delete()
        db.session.commit()
        flash('All analytics data cleared.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error clearing analytics: ' + str(e), 'error')
    return redirect(url_for('admin_analytics'))

@app.route('/admin/analytics/export.csv')
@admin_required
def admin_analytics_export():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Type', 'Page/Section', 'IP', 'User Agent', 'Timestamp'])
    for v in PageView.query.order_by(PageView.timestamp.desc()).limit(5000):
        writer.writerow(['pageview', v.page, v.ip_address or '', v.user_agent or '', v.timestamp])
    for i in Interest.query.order_by(Interest.timestamp.desc()).limit(5000):
        writer.writerow(['interest', f"{i.section}/{i.action}", i.ip_address or '', '', i.timestamp])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=analytics.csv'})

# ----- Fun Facts -----

@app.route('/admin/fun-facts')
@admin_required
def admin_fun_facts():
    facts = FunFact.query.order_by(FunFact.updated_at.desc()).all()
    return render_template('admin/fun_facts.html', facts=facts)

@app.route('/admin/fun-facts/add', methods=['GET', 'POST'])
@admin_required
def admin_fun_fact_add():
    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        if not text:
            flash('Fun fact text is required.', 'error')
            return redirect(url_for('admin_fun_fact_add'))
        fact = FunFact(text=text, active=bool(request.form.get('active')))
        db.session.add(fact)
        db.session.commit()
        flash('Fun fact added.', 'success')
        return redirect(url_for('admin_fun_facts'))
    return render_template('admin/fun_fact_form.html', fact=None)

@app.route('/admin/fun-facts/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_fun_fact_edit(id):
    fact = FunFact.query.get_or_404(id)
    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        if not text:
            flash('Fun fact text is required.', 'error')
            return redirect(url_for('admin_fun_fact_edit', id=id))
        fact.text = text
        fact.active = bool(request.form.get('active'))
        db.session.commit()
        flash('Fun fact updated.', 'success')
        return redirect(url_for('admin_fun_facts'))
    return render_template('admin/fun_fact_form.html', fact=fact)

@app.route('/admin/fun-facts/delete/<int:id>', methods=['POST'])
@admin_required
def admin_fun_fact_delete(id):
    fact = FunFact.query.get_or_404(id)
    db.session.delete(fact)
    db.session.commit()
    flash('Fun fact deleted.', 'success')
    return redirect(url_for('admin_fun_facts'))

# ----- Testimonials -----

@app.route('/admin/testimonials')
@admin_required
def admin_testimonials():
    testimonials = Testimonial.query.order_by(Testimonial.sort_order).all()
    return render_template('admin/testimonials.html', testimonials=testimonials)

@app.route('/admin/testimonials/add', methods=['GET', 'POST'])
@admin_required
def admin_testimonial_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        text = request.form.get('text', '').strip()
        if not name or not text:
            flash('Name and text are required.', 'error')
            return redirect(url_for('admin_testimonial_add'))
        avatar = ''
        if request.files.get('avatar'):
            file = request.files['avatar']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                avatar = filename
        testimonial = Testimonial(name=name, role=request.form.get('role', ''),
            text=text, avatar_filename=avatar,
            active=bool(request.form.get('active')),
            sort_order=int(request.form.get('sort_order', 0)))
        db.session.add(testimonial)
        db.session.commit()
        flash('Testimonial added.', 'success')
        return redirect(url_for('admin_testimonials'))
    return render_template('admin/testimonial_form.html', testimonial=None)

@app.route('/admin/testimonials/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_testimonial_edit(id):
    testimonial = Testimonial.query.get_or_404(id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        text = request.form.get('text', '').strip()
        if not name or not text:
            flash('Name and text are required.', 'error')
            return redirect(url_for('admin_testimonial_edit', id=id))
        testimonial.name = name
        testimonial.role = request.form.get('role', '')
        testimonial.text = text
        testimonial.active = bool(request.form.get('active'))
        testimonial.sort_order = int(request.form.get('sort_order', 0))
        if request.files.get('avatar') and request.files['avatar'].filename:
            file = request.files['avatar']
            if allowed_file(file.filename):
                if testimonial.avatar_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], testimonial.avatar_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                testimonial.avatar_filename = filename
        db.session.commit()
        flash('Testimonial updated.', 'success')
        return redirect(url_for('admin_testimonials'))
    return render_template('admin/testimonial_form.html', testimonial=testimonial)

@app.route('/admin/testimonials/delete/<int:id>', methods=['POST'])
@admin_required
def admin_testimonial_delete(id):
    testimonial = Testimonial.query.get_or_404(id)
    if testimonial.avatar_filename:
        path = os.path.join(app.config['UPLOAD_FOLDER'], testimonial.avatar_filename)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(testimonial)
    db.session.commit()
    flash('Testimonial deleted.', 'success')
    return redirect(url_for('admin_testimonials'))

# ----- Blog -----

@app.route('/admin/blog')
@admin_required
def admin_blog():
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    return render_template('admin/blog.html', posts=posts)

@app.route('/admin/blog/add', methods=['GET', 'POST'])
@admin_required
def admin_blog_add():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('Title and content are required.', 'error')
            return redirect(url_for('admin_blog_add'))
        slug = slugify(title)
        existing = BlogPost.query.filter_by(slug=slug).first()
        if existing:
            slug = f"{slug}-{int(datetime.now().timestamp())}"
        image = ''
        if request.files.get('image'):
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename
        post = BlogPost(title=title, slug=slug, content=content,
            summary=request.form.get('summary', ''),
            image_filename=image,
            published=bool(request.form.get('published')))
        db.session.add(post)
        db.session.commit()
        flash('Blog post created.', 'success')
        return redirect(url_for('admin_blog'))
    return render_template('admin/blog_form.html', post=None)

@app.route('/admin/blog/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_blog_edit(id):
    post = BlogPost.query.get_or_404(id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('Title and content are required.', 'error')
            return redirect(url_for('admin_blog_edit', id=id))
        post.title = title
        post.content = content
        post.summary = request.form.get('summary', '')
        post.published = bool(request.form.get('published'))
        if request.files.get('image') and request.files['image'].filename:
            file = request.files['image']
            if allowed_file(file.filename):
                if post.image_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                post.image_filename = filename
        db.session.commit()
        flash('Blog post updated.', 'success')
        return redirect(url_for('admin_blog'))
    return render_template('admin/blog_form.html', post=post)

@app.route('/admin/blog/delete/<int:id>', methods=['POST'])
@admin_required
def admin_blog_delete(id):
    post = BlogPost.query.get_or_404(id)
    if post.image_filename:
        path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(post)
    db.session.commit()
    flash('Blog post deleted.', 'success')
    return redirect(url_for('admin_blog'))

# ----- Subscribers -----

@app.route('/admin/subscribers')
@admin_required
def admin_subscribers():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    subscribers = Subscriber.query.order_by(Subscriber.created_at.desc()).paginate(page=page, per_page=per_page)
    return render_template('admin/subscribers.html', subscribers=subscribers)

@app.route('/admin/subscribers/export.csv')
@admin_required
def admin_subscribers_export():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Email', 'Name', 'Source', 'Brevo Synced', 'Active', 'Subscribed At'])
    for s in Subscriber.query.order_by(Subscriber.created_at.desc()).all():
        writer.writerow([s.email, s.name or '', s.source, 'Yes' if s.brevo_synced else 'No', 'Yes' if s.active else 'No', s.created_at])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=subscribers.csv'})

with app.app_context():
    db.create_all()
    try:
        import sqlalchemy as sa
        inspector = sa.inspect(db.engine)
        cols = [c['name'] for c in inspector.get_columns('subscriber')]
        if 'validated' not in cols:
            db.session.execute(sa.text('ALTER TABLE subscriber ADD COLUMN validated BOOLEAN DEFAULT 0'))
            db.session.commit()
            print('Added validated column to subscriber table.')
    except Exception as e:
        print('Startup note (migration):', e)
        db.session.rollback()
    if not User.query.first():
        hashed = bcrypt.generate_password_hash('admin123').decode('utf-8')
        db.session.add(User(username='admin', password_hash=hashed))
        db.session.commit()
        print('Default admin user created: admin / admin123')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
