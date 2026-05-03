from flask import Flask, render_template, redirect, url_for, flash, request, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'housing-committee-secret-key-2026')

# Render: если задан DATABASE_PATH — используем его (persistent disk /data)
# Иначе — стандартный путь для локальной разработки
_db_path = os.environ.get('DATABASE_PATH')
if _db_path:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + _db_path
else:
    _base = os.path.abspath(os.path.dirname(__file__))
    _instance = os.path.join(_base, 'instance')
    os.makedirs(_instance, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(_instance, 'housing.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'


# ─── MODELS ─────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    full_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='author', lazy=True)
    applications = db.relationship('Application', backref='applicant', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.String(500))
    category = db.Column(db.String(100))
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_name = db.Column(db.String(200))
    is_published = db.Column(db.Boolean, default=True)


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    content = db.Column(db.Text, nullable=False)
    section = db.Column(db.String(100))  # 'services', 'documents', 'legislation', 'faq', 'residents'
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_name = db.Column(db.String(200))


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    applicant_name = db.Column(db.String(200), nullable=False)
    applicant_email = db.Column(db.String(120))
    applicant_phone = db.Column(db.String(50))
    subject = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=False)
    app_type = db.Column(db.String(100))  # тип обращения
    status = db.Column(db.String(50), default='new')  # new, in_progress, resolved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    response = db.Column(db.Text)
    resolved_at = db.Column(db.DateTime)

    @property
    def body(self):
        return self.description

    @property
    def admin_reply(self):
        return self.response

    @property
    def user(self):
        return User.query.get(self.user_id) if self.user_id else None

    @property
    def app_type_label(self):
        labels = {
            'repair': 'Ремонт',
            'utility': 'Коммунальные услуги',
            'noise': 'Шум',
            'parking': 'Парковка',
            'landscaping': 'Благоустройство',
            'document': 'Документы',
            'complaint': 'Жалоба',
            'suggestion': 'Предложение',
            'other': 'Прочее',
        }
        return labels.get(self.app_type, self.app_type or 'Прочее')


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    is_admin_reply = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)

    @property
    def body(self):
        return self.content

    @property
    def is_admin(self):
        return self.is_admin_reply


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── HELPERS ────────────────────────────────────────────────────────────────

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─── ROUTES: PUBLIC ─────────────────────────────────────────────────────────

@app.route('/')
def index():
    latest_news = News.query.filter_by(is_published=True).order_by(News.published_at.desc()).limit(5).all()
    return render_template('index.html', news=latest_news)


@app.route('/news')
def news():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    q = News.query.filter_by(is_published=True)
    if category:
        q = q.filter_by(category=category)
    pagination = q.order_by(News.published_at.desc()).paginate(page=page, per_page=6, error_out=False)
    categories = db.session.query(News.category).distinct().all()
    return render_template('news.html', pagination=pagination, current_category=category,
                           categories=[c[0] for c in categories if c[0]])


@app.route('/news/<int:news_id>')
def news_detail(news_id):
    item = News.query.get_or_404(news_id)
    related = News.query.filter(News.id != news_id, News.is_published == True).order_by(News.published_at.desc()).limit(3).all()
    return render_template('news_detail.html', item=item, related=related)


@app.route('/services')
def services():
    articles = Article.query.filter_by(section='services').order_by(Article.published_at.desc()).all()
    return render_template('services.html', articles=articles)


@app.route('/documents')
def documents():
    articles = Article.query.filter_by(section='documents').order_by(Article.published_at.desc()).all()
    return render_template('documents.html', articles=articles)


@app.route('/legislation')
def legislation():
    articles = Article.query.filter_by(section='legislation').order_by(Article.published_at.desc()).all()
    return render_template('legislation.html', articles=articles)


@app.route('/residents')
def residents():
    articles = Article.query.filter_by(section='residents').order_by(Article.published_at.desc()).all()
    return render_template('residents.html', articles=articles)


@app.route('/faq')
def faq():
    articles = Article.query.filter_by(section='faq').order_by(Article.published_at.desc()).all()
    return render_template('faq.html', articles=articles)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/contacts')
def contacts():
    return render_template('contacts.html')


@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    results_news = []
    results_articles = []
    if q:
        like = f'%{q}%'
        results_news = News.query.filter(
            News.is_published == True,
            (News.title.ilike(like) | News.content.ilike(like))
        ).limit(10).all()
        results_articles = Article.query.filter(
            Article.title.ilike(like) | Article.content.ilike(like)
        ).limit(10).all()
    return render_template('search.html', q=q, results_news=results_news, results_articles=results_articles)


@app.route('/sitemap')
def sitemap():
    return render_template('sitemap.html')


# ─── ROUTES: AUTH ───────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Добро пожаловать!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('Неверный логин или пароль.', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if password != confirm:
            flash('Пароли не совпадают.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Пользователь с таким логином уже существует.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Этот e-mail уже зарегистрирован.', 'danger')
        elif len(password) < 6:
            flash('Пароль должен содержать не менее 6 символов.', 'danger')
        else:
            user = User(username=username, email=email, full_name=full_name, role='user')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Регистрация прошла успешно!', 'success')
            return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))


# ─── ROUTES: USER CABINET ───────────────────────────────────────────────────

@app.route('/cabinet')
@login_required
def cabinet():
    apps = Application.query.filter_by(user_id=current_user.id).order_by(Application.created_at.desc()).all()
    msgs = Message.query.filter_by(user_id=current_user.id, is_admin_reply=False).order_by(Message.created_at.desc()).all()
    return render_template('cabinet.html', applications=apps, messages=msgs)


@app.route('/apply', methods=['GET', 'POST'])
@login_required
def apply():
    if request.method == 'POST':
        app_obj = Application(
            user_id=current_user.id,
            applicant_name=request.form.get('applicant_name', '').strip(),
            applicant_email=request.form.get('applicant_email', '').strip(),
            applicant_phone=request.form.get('applicant_phone', '').strip(),
            subject=request.form.get('subject', '').strip(),
            description=request.form.get('description', '').strip(),
            app_type=request.form.get('app_type', '').strip(),
        )
        db.session.add(app_obj)
        db.session.commit()
        flash('Обращение успешно отправлено! Мы свяжемся с вами в течение 3 рабочих дней.', 'success')
        return redirect(url_for('cabinet'))
    return render_template('apply.html')


@app.route('/messages', methods=['GET', 'POST'])
@login_required
def messages():
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            msg = Message(user_id=current_user.id, content=content)
            db.session.add(msg)
            db.session.commit()
            flash('Сообщение отправлено.', 'success')
    user_msgs = Message.query.filter_by(user_id=current_user.id).order_by(Message.created_at.asc()).all()
    return render_template('messages.html', messages=user_msgs)


# ─── ROUTES: ADMIN ──────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    stats = {
        'users': User.query.count(),
        'news': News.query.count(),
        'articles': Article.query.count(),
        'applications': Application.query.count(),
        'new_applications': Application.query.filter_by(status='new').count(),
        'messages': Message.query.filter_by(is_read=False, is_admin_reply=False).count(),
    }
    recent_apps = Application.query.order_by(Application.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html', stats=stats, recent_apps=recent_apps)


@app.route('/admin/news', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_news():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            item = News(
                title=request.form.get('title'),
                content=request.form.get('content'),
                excerpt=request.form.get('excerpt'),
                category=request.form.get('category'),
                author_name=request.form.get('author_name', current_user.full_name or current_user.username),
                is_published=bool(request.form.get('is_published'))
            )
            db.session.add(item)
            db.session.commit()
            flash('Новость добавлена.', 'success')
        elif action == 'delete':
            item = News.query.get(request.form.get('news_id'))
            if item:
                db.session.delete(item)
                db.session.commit()
                flash('Новость удалена.', 'info')
    news_list = News.query.order_by(News.published_at.desc()).all()
    return render_template('admin/news.html', news_list=news_list)


@app.route('/admin/articles', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_articles():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            item = Article(
                title=request.form.get('title'),
                content=request.form.get('content'),
                section=request.form.get('section'),
                author_name=request.form.get('author_name', current_user.full_name or current_user.username)
            )
            db.session.add(item)
            db.session.commit()
            flash('Статья добавлена.', 'success')
        elif action == 'delete':
            item = Article.query.get(request.form.get('article_id'))
            if item:
                db.session.delete(item)
                db.session.commit()
                flash('Статья удалена.', 'info')
    articles = Article.query.order_by(Article.published_at.desc()).all()
    return render_template('admin/articles.html', articles=articles)


@app.route('/admin/applications')
@login_required
@admin_required
def admin_applications():
    status_filter = request.args.get('status', '')
    type_filter = request.args.get('type', '')
    q = Application.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    if type_filter:
        q = q.filter_by(app_type=type_filter)
    applications = q.order_by(Application.created_at.desc()).all()
    return render_template('admin/applications.html', applications=applications)


@app.route('/admin/applications/<int:app_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_application_detail(app_id):
    application = Application.query.get_or_404(app_id)
    if request.method == 'POST':
        application.status = request.form.get('status', application.status)
        reply = request.form.get('reply', '').strip()
        if reply:
            application.response = reply
            application.resolved_at = datetime.utcnow()
        application.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Обращение обновлено.', 'success')
    return render_template('admin/application_detail.html', application=application)


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/messages')
@login_required
@admin_required
def admin_messages():
    # Build dialogs list with last message and unread count
    users_with_msgs = db.session.query(User).join(Message, User.id == Message.user_id).distinct().all()
    dialogs = []
    for u in users_with_msgs:
        last_msg = Message.query.filter_by(user_id=u.id).order_by(Message.created_at.desc()).first()
        unread = Message.query.filter_by(user_id=u.id, is_admin_reply=False, is_read=False).count()
        if last_msg:
            dialogs.append({'user': u, 'last_message': last_msg, 'unread': unread})
    dialogs.sort(key=lambda x: x['last_message'].created_at, reverse=True)
    return render_template('admin/messages.html', dialogs=dialogs)


@app.route('/admin/messages/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_message_thread(user_id):
    thread_user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if body:
            msg = Message(user_id=user_id, content=body, is_admin_reply=True, is_read=True)
            db.session.add(msg)
            Message.query.filter_by(user_id=user_id, is_admin_reply=False, is_read=False).update({'is_read': True})
            db.session.commit()
            flash('Ответ отправлен.', 'success')
            return redirect(request.url)
    messages = Message.query.filter_by(user_id=user_id).order_by(Message.created_at.asc()).all()
    return render_template('admin/message_thread.html', thread_user=thread_user, messages=messages)


@app.route('/toggle_vi')
def toggle_vi():
    session['vi_mode'] = not session.get('vi_mode', False)
    return redirect(request.referrer or url_for('index'))


# ─── ERROR HANDLERS ─────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


# ─── INIT DB ────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        # Admin user
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@housing-committee.ru',
                         full_name='Администратор Системы', role='admin')
            admin.set_password('Admin2026!')
            db.session.add(admin)

        # Regular user
        if not User.query.filter_by(username='ivanov').first():
            user = User(username='ivanov', email='ivanov@mail.ru',
                        full_name='Иванов Иван Иванович', role='user')
            user.set_password('User2026!')
            db.session.add(user)

        db.session.commit()
        _seed_content()


def _seed_content():
    from datetime import date, timedelta
    import random

    if News.query.count() > 0:
        return

    # ── NEWS ────────────────────────────────────────────────────────────────
    base = datetime(2026, 5, 25)
    news_data = [
        ("Плановое отключение горячей воды: актуальный график на июнь 2026", "объявления",
         """В связи с проведением профилактических работ на тепловых сетях города в период с 1 по 14 июня 2026 года будет осуществлено плановое отключение горячего водоснабжения в ряде жилых домов. Работы проводятся в соответствии с планом ТО, утверждённым распоряжением Жилищного комитета № 47-р от 12 мая 2026 года.

Отключения затронут следующие районы:
— Центральный район: дома по ул. Советской (чётная сторона), ул. Ленина 1–40;
— Северный район: кварталы 5А, 6Б, 7В;
— Западный район: ул. Мира 10–35, ул. Гагарина 2–18.

Жилищный комитет рекомендует жителям заблаговременно запастись запасами воды. Техническая служба доступна по телефону 8-800-100-10-10 (звонок бесплатный) круглосуточно в период проведения работ. По окончании каждого этапа работ горячее водоснабжение будет восстановлено в течение 4 часов.""",
         "Подача горячей воды будет временно приостановлена в связи с плановыми профилактическими работами.", "Отдел ЖКХ"),

        ("Открытие нового МФЦ в Северном районе: расширение услуг для жителей", "события",
         """1 июня 2026 года в Северном районе торжественно открылся новый многофункциональный центр «Мои документы». МФЦ расположен по адресу: пр. Северный, д. 15, корп. 2 и готов принимать жителей ежедневно с 8:00 до 20:00, в субботу — с 9:00 до 17:00.

Перечень доступных услуг включает:
— оформление субсидий на оплату ЖКУ;
— приём заявлений на улучшение жилищных условий;
— выдача справок о составе семьи и истории жилого помещения;
— регистрация договоров социального найма;
— консультации по капитальному ремонту.

На открытии присутствовал председатель Жилищного комитета, который отметил, что создание нового МФЦ сократит время ожидания в очереди на 40% и существенно повысит доступность государственных услуг для жителей северных кварталов. Запись на приём доступна через портал Госуслуги и на официальном сайте МФЦ.""",
         "В Северном районе открылся новый центр государственных услуг в сфере ЖКХ.", "Пресс-служба"),

        ("Программа капитального ремонта 2026: 120 домов получат обновление", "программы",
         """Жилищный комитет утвердил расширенную программу капитального ремонта на 2026 год. В перечень вошли 120 многоквартирных домов общей площадью свыше 850 000 кв. м. Общий объём финансирования составляет 2,4 млрд рублей из регионального фонда капитального ремонта.

Приоритетные виды работ в 2026 году:
— замена лифтового оборудования — 47 домов;
— ремонт кровли и гидроизоляция — 38 домов;
— модернизация инженерных систем отопления — 23 дома;
— комплексный ремонт фасадов — 12 домов.

Жители домов, включённых в программу, будут уведомлены заказными письмами не позднее 30 дней до начала работ. Контроль за качеством выполнения работ осуществляется отделом технического надзора Жилищного комитета. Гражданам предоставляется право общественного контроля: уполномоченный представитель дома может входить в состав приёмочной комиссии.""",
         "Утверждён список домов для капитального ремонта — 120 объектов по всему городу.", "Отдел капремонта"),

        ("Субсидии на оплату ЖКУ: новые правила оформления с июня 2026", "льготы",
         """С 1 июня 2026 года вступают в силу изменения в порядке назначения жилищных субсидий, предусмотренные Постановлением Правительства РФ № 215. Основные нововведения направлены на упрощение процедуры и расширение круга получателей.

Ключевые изменения:
— порог расходов на ЖКУ для назначения субсидии снижен с 22% до 18% дохода семьи;
— перечень необходимых документов сокращён: теперь не требуется предоставление квитанций об отсутствии долгов (сведения запрашиваются в рамках межведомственного взаимодействия);
— срок рассмотрения заявления сокращён с 10 до 7 рабочих дней;
— субсидия теперь может быть оформлена дистанционно через портал Госуслуги.

Для получения субсидии необходимо: подать заявление (лично, через МФЦ или Госуслуги), предоставить паспорт, документы о праве собственности или найма, справки о доходах всех членов семьи за последние 6 месяцев.""",
         "С июня расширяется доступность субсидий — упрощение документов и снижение порога.", "Отдел льгот и субсидий"),

        ("Жилищный контроль 2026: итоги проверок управляющих компаний", "отчёты",
         """По результатам плановых и внеплановых проверок управляющих компаний за I квартал 2026 года Жилищный комитет подвёл итоговый отчёт. Проверено 87 управляющих организаций, обслуживающих 1 240 многоквартирных домов.

Основные выявленные нарушения:
— несоблюдение сроков устранения аварийных ситуаций — 23% УК;
— ненадлежащее содержание придомовых территорий — 18% УК;
— отсутствие обязательной отчётности перед собственниками — 31% УК;
— нарушения в ведении технической документации — 14% УК.

По итогам проверок выдано 64 предписания об устранении нарушений, возбуждено 12 административных дел. Жилищный комитет напоминает гражданам об их праве подавать жалобы на управляющие компании через официальный сайт или по телефону горячей линии.""",
         "Опубликованы результаты проверок управляющих компаний за I квартал 2026 года.", "Контрольный отдел"),

        ("Аварийное жильё: расселение 14 домов завершено досрочно", "программы",
         """Жилищный комитет сообщает о досрочном завершении расселения 14 аварийных многоквартирных домов в рамках региональной программы «Переселение из аварийного жилья 2022–2026». Все 347 семей (912 человек) получили новые квартиры в современных жилых комплексах.

Новосёлы переехали в дома, построенные по программе жилищного строительства в микрорайонах «Солнечный», «Зелёный берег» и «Новый город». Средняя площадь предоставленных квартир составила 52 кв. м, что на 8% больше, чем у оставленного аварийного жилья.

Освободившиеся земельные участки планируется использовать для создания общественных пространств: парков, детских площадок и зон отдыха. Проекты благоустройства разрабатываются совместно с жителями в формате общественных обсуждений.""",
         "Завершено расселение 347 семей из аварийных домов — все получили новые квартиры.", "Отдел переселения"),
    ]
    for i, (title, cat, content, excerpt, author) in enumerate(news_data):
        dt = base + timedelta(days=i * 2)
        n = News(title=title, category=cat, content=content, excerpt=excerpt,
                 author_name=author, published_at=dt, is_published=True)
        db.session.add(n)

    # ── ARTICLES ────────────────────────────────────────────────────────────
    articles_data = [
        # SERVICES
        ("services", "Как подать заявление на улучшение жилищных условий",
         """Граждане, нуждающиеся в улучшении жилищных условий, вправе обратиться в Жилищный комитет с соответствующим заявлением. Право на постановку в очередь имеют семьи, обеспеченные жильём ниже установленной нормы (менее 10 кв. м на человека), а также граждане, проживающие в аварийном или ветхом жилом фонде.

Для подачи заявления необходимо:
1. Заполнить заявление установленного образца (форма Ж-1).
2. Предоставить паспорта всех членов семьи.
3. Справку о составе семьи (форма 9).
4. Документы о праве пользования жильём (свидетельство о собственности, договор найма).
5. Справки о доходах за последние 12 месяцев.
6. Справку БТИ о наличии/отсутствии имущества.

Заявление рассматривается в течение 30 рабочих дней. О решении заявитель уведомляется письменно. В случае отказа гражданин вправе обжаловать решение в судебном порядке или через вышестоящую инстанцию.""",
         "Жилищный комитет"),
        ("services", "Приватизация жилья: пошаговая инструкция",
         """Приватизация — это безвозмездная передача жилого помещения из муниципальной или государственной собственности в собственность граждан, проживающих в нём на основании договора социального найма.

Право на приватизацию имеет каждый гражданин РФ один раз в жизни. Исключение составляют несовершеннолетние, которые после достижения 18 лет сохраняют право на приватизацию в полном объёме.

Порядок оформления:
Шаг 1. Обратитесь в МФЦ или Жилищный комитет и получите список необходимых документов.
Шаг 2. Подготовьте пакет документов: паспорта, документы БТИ, выписку из домовой книги, ордер или договор найма.
Шаг 3. Подайте заявление — лично, через МФЦ или портал Госуслуги.
Шаг 4. В течение 46 рабочих дней Жилищный комитет рассматривает заявление и выдаёт договор о приватизации.
Шаг 5. Зарегистрируйте право собственности в Росреестре.""",
         "Отдел приватизации"),
        ("services", "Признание жилья аварийным: кто принимает решение и как",
         """Признание многоквартирного дома аварийным или ветхим — сложная процедура, от результатов которой зависит дальнейшая судьба жилья и его жильцов. Решение принимает межведомственная комиссия на основании обследования технического состояния конструкций.

Основания для признания аварийным: физический износ конструкций свыше 70%, деформации несущих элементов, угроза обрушения, повреждение в результате стихийного бедствия или техногенной катастрофы.

Обращение в комиссию вправе подать: сам собственник, орган государственного жилищного надзора, орган государственного контроля (надзора) в сфере строительства. Жители дома могут инициировать обследование, подав коллективное обращение в Жилищный комитет.""",
         "Технический отдел"),
        ("services", "Договор социального найма: оформление и переоформление",
         """Договор социального найма — основной документ, подтверждающий право пользования жилым помещением муниципального жилого фонда. Договор заключается с нанимателем — гражданином, достигшим 18 лет, и не имеет срока действия.

Договор подлежит переоформлению в следующих случаях:
— смерть нанимателя (переоформление на члена семьи);
— изменение состава семьи нанимателя;
— изменение адреса или характеристик жилого помещения.

Для заключения договора необходимы: решение о предоставлении жилого помещения, паспорта, справка о составе семьи. Срок оформления — 10 рабочих дней. Договор выдаётся в 2 экземплярах: один остаётся у нанимателя, второй хранится в Жилищном комитете.""",
         "Отдел найма"),
        ("services", "Субсидии на капитальный ремонт: льготные категории граждан",
         """Действующее законодательство предусматривает льготы по уплате взносов на капитальный ремонт для ряда категорий граждан. Компенсация предоставляется в форме возмещения фактически понесённых расходов.

Право на льготу имеют:
— одиноко проживающие собственники, достигшие 70 лет — компенсация 50%;
— одиноко проживающие собственники, достигшие 80 лет — компенсация 100%;
— инвалиды I и II группы — компенсация 50%;
— семьи, имеющие в составе детей-инвалидов — компенсация 50%;
— ветераны труда (в соответствии с региональным законодательством) — 50%.

Для оформления компенсации следует обратиться в МФЦ или Жилищный комитет с паспортом, документом о праве собственности, документом, подтверждающим льготный статус, и квитанциями об уплате взносов.""",
         "Отдел льгот и субсидий"),

        # DOCUMENTS
        ("documents", "Перечень документов для постановки на жилищный учёт",
         """Для постановки на учёт нуждающихся в жилых помещениях необходимо предоставить следующий комплект документов в Жилищный комитет или МФЦ:

Обязательные документы:
1. Заявление о принятии на учёт (заполняется на месте или скачивается на сайте).
2. Паспорта и свидетельства о рождении всех членов семьи.
3. Свидетельство о браке/разводе (при наличии).
4. Справка о составе семьи (форма 9, не старше 1 месяца).
5. Документы о праве пользования жильём.
6. Справки о доходах всех трудоспособных членов семьи за 12 месяцев.
7. Справка об имуществе на праве собственности (из Росреестра).

Дополнительные документы (при наличии оснований):
— медицинское заключение (при наличии хронического заболевания из Перечня);
— документы об аварийности жилья;
— документы льготных категорий (удостоверения, справки МСЭ и т.д.).""",
         "Отдел учёта"),
        ("documents", "Формы заявлений для скачивания",
         """На данной странице размещены актуальные формы заявлений, используемых при обращении в Жилищный комитет. Все формы соответствуют требованиям действующего законодательства и обновляются при изменении нормативной базы.

Доступные формы:
— Форма Ж-1: Заявление о постановке на жилищный учёт
— Форма Ж-2: Заявление о приватизации жилого помещения
— Форма Ж-3: Заявление на предоставление субсидии на оплату ЖКУ
— Форма Ж-4: Заявление о признании жилья аварийным
— Форма Ж-5: Заявление об изменении договора социального найма
— Форма Ж-6: Заявление на компенсацию взносов на капремонт

Все формы доступны в форматах .docx и .pdf. При затруднении с заполнением вы можете обратиться на бесплатную консультацию к специалистам Жилищного комитета (предварительная запись по тел. 8-800-100-10-10).""",
         "Канцелярия"),
        ("documents", "Справки и выписки: где и как получить",
         """Жилищный комитет выдаёт следующие виды справок и выписок:

1. Справка о составе семьи (форма 9) — подтверждает состав зарегистрированных лиц.
2. Справка о регистрации (форма 8) — подтверждает факт регистрации по месту жительства.
3. Выписка из домовой книги — полная история регистрационного учёта по адресу.
4. Справка об отсутствии задолженности по ЖКУ.
5. Справка о нахождении в жилищной очереди.

Способы получения:
— Лично в Жилищном комитете: пн–пт с 9:00 до 17:00, приёмные дни вт и чт.
— Через МФЦ «Мои документы»: ежедневно с 8:00 до 20:00.
— Через портал Госуслуги: электронная форма, срок — 3 рабочих дня.

Справки выдаются бесплатно. Срок действия большинства справок — 30 дней.""",
         "Канцелярия"),
        ("documents", "Требования к фотографиям и копиям документов",
         """При подаче документов в Жилищный комитет необходимо соблюдать следующие требования к копиям и фотоматериалам:

Копии документов:
— должны быть читаемыми, без обрезки реквизитов;
— для документов с двух сторон — необходимо копировать обе стороны;
— нотариальное заверение не требуется, но при подаче необходимо предъявить оригиналы.

Фотографии (при необходимости):
— формат 3×4 см или 4×6 см (указано в бланке заявления);
— цветные, на светлом фоне;
— сделаны не ранее чем 6 месяцев назад.

Электронные документы:
— форматы: PDF, JPG, PNG с разрешением не менее 150 dpi;
— размер файла — не более 5 МБ;
— сканирование должно быть чётким, без бликов и теней.

При несоответствии требованиям документы могут быть возвращены заявителю.""",
         "Канцелярия"),
        ("documents", "Архивные документы на жильё: куда обращаться",
         """Для получения архивных документов, связанных с жилыми помещениями, следует обращаться в соответствующие организации в зависимости от типа документа:

БТИ (Бюро технической инвентаризации):
— технические паспорта на жилые помещения;
— справки о стоимости имущества;
— сведения об изменениях конструктивных характеристик.

Жилищный комитет (архивный отдел):
— архивные выписки из домовых книг;
— документы о приватизации, выданные до 1998 года;
— ордера на жилые помещения.

Росреестр:
— сведения о переходе прав собственности;
— выписки из ЕГРН за любой период.

Срок исполнения архивных запросов — от 10 до 30 рабочих дней. Рекомендуем обращаться заблаговременно, особенно при подготовке к судебным разбирательствам или сделкам с недвижимостью.""",
         "Архивный отдел"),

        # LEGISLATION
        ("legislation", "Жилищный кодекс РФ: ключевые положения для граждан",
         """Жилищный кодекс Российской Федерации (ЖК РФ) — основной нормативный акт, регулирующий жилищные правоотношения. Принят 29 декабря 2004 года, введён в действие 1 марта 2005 года.

Наиболее важные разделы для граждан:

Раздел II — Право собственности и другие вещные права:
определяет права и обязанности собственников жилых помещений, правовой режим общего имущества МКД.

Раздел III — Жилые помещения, предоставляемые по договорам социального найма:
регулирует основания и порядок предоставления жилья, права и обязанности нанимателей.

Раздел V — Жилищно-коммунальное хозяйство:
устанавливает правила управления МКД, права и обязанности управляющих организаций.

Раздел VIII — Управление многоквартирными домами:
определяет способы управления МКД, порядок проведения общих собраний собственников.""",
         "Юридический отдел"),
        ("legislation", "Федеральный закон № 185-ФЗ о Фонде содействия реформированию ЖКХ",
         """Федеральный закон от 21 июля 2007 года № 185-ФЗ «О Фонде содействия реформированию жилищно-коммунального хозяйства» заложил правовую основу государственной поддержки капитального ремонта и расселения аварийного жилья в России.

Основные положения, актуальные для граждан:
— государство предоставляет финансовую поддержку регионам на капитальный ремонт МКД и переселение из аварийного жилья;
— условием получения поддержки является соответствие региональных программ федеральным требованиям;
— гражданам гарантировано равнозначное жильё при переселении из аварийных домов;
— закон устанавливает механизм общественного контроля за расходованием средств.

Действие закона неоднократно продлевалось. В настоящее время программа расселения аварийного жилья действует до 2026 года включительно.""",
         "Юридический отдел"),
        ("legislation", "Постановление Правительства о минимальном размере взноса на капремонт",
         """Размер минимального взноса на капитальный ремонт устанавливается нормативным актом субъекта Российской Федерации на каждый год. Методика расчёта определена Постановлением Правительства РФ от 26 декабря 2016 года № 1498.

Факторы, влияющие на размер взноса:
— год постройки и тип конструктивных элементов дома;
— наличие лифтового оборудования;
— этажность здания;
— перечень услуг и работ по капитальному ремонту.

В нашем регионе на 2026 год установлены следующие размеры взносов:
— для домов до 5 этажей без лифта: 8,52 руб./кв. м в месяц;
— для домов 6–9 этажей: 10,36 руб./кв. м в месяц;
— для домов 10 этажей и выше: 12,74 руб./кв. м в месяц.

Собственники, использующие спецсчёт, вправе принять решение об увеличении взноса выше минимального уровня.""",
         "Юридический отдел"),
        ("legislation", "Права собственников при проведении общего собрания",
         """Общее собрание собственников помещений в многоквартирном доме (ОСС) является высшим органом управления МКД. Порядок его проведения регулируется статьями 44–48 Жилищного кодекса РФ.

Права собственников на ОСС:
— право инициировать проведение собрания (при наличии 10% и более голосов);
— право участвовать в голосовании лично или через представителя по доверенности;
— право знакомиться с документацией, связанной с повесткой дня;
— право обжаловать решение ОСС в суде в течение 6 месяцев.

Собрание правомочно при участии собственников, обладающих более 50% голосов от общего числа. Решения по большинству вопросов принимаются простым большинством, по ряду вопросов — 2/3 голосов.""",
         "Юридический отдел"),
        ("legislation", "Закон о защите прав потребителей в сфере ЖКУ",
         """Отношения между потребителями жилищно-коммунальных услуг и их исполнителями регулируются Законом РФ «О защите прав потребителей» (применяется в части, не урегулированной жилищным законодательством) и Правилами предоставления коммунальных услуг (Постановление Правительства РФ № 354).

Права потребителей ЖКУ:
— получать услуги установленного качества бесперебойно, за исключением случаев, предусмотренных законодательством;
— требовать перерасчёта платы при предоставлении услуг ненадлежащего качества или с перерывами;
— проверять правильность начисления платы (раз в год бесплатно);
— требовать компенсации ущерба, причинённого ненадлежащим исполнением услуг.

При нарушении прав следует обратиться: в управляющую компанию → в ГЖИ → в суд или Роспотребнадзор.""",
         "Юридический отдел"),

        # FAQ
        ("faq", "Как узнать свою очередь на получение жилья?",
         """Информацию о положении в жилищной очереди можно получить несколькими способами:

1. Личное обращение в Жилищный комитет.
Приёмные дни: вторник и четверг с 10:00 до 16:00. При себе иметь паспорт и документы, подтверждающие постановку на учёт.

2. Запрос через МФЦ.
Подайте запрос в любом отделении МФЦ «Мои документы». Ответ будет направлен в течение 5 рабочих дней.

3. Личный кабинет на сайте.
После регистрации и подтверждения личности вы можете просматривать актуальный номер очереди в личном кабинете на нашем сайте.

4. Портал Госуслуги.
Через раздел «ЖКХ» → «Жилищный учёт» → «Узнать номер очереди».

Обратите внимание: номер в очереди может меняться — как уменьшаться (при снятии с учёта граждан, стоявших перед вами), так и увеличиваться (при добавлении льготников, имеющих преимущественное право).""",
         "Справочная служба"),
        ("faq", "Что делать, если управляющая компания не выполняет обязательства?",
         """Если управляющая компания (УК) не выполняет принятые на себя обязательства, у собственников есть несколько механизмов защиты своих прав:

Шаг 1. Подайте претензию в управляющую компанию.
Оформите обращение письменно, укажите конкретные нарушения, сроки и требования. Претензия регистрируется и должна быть рассмотрена в течение 10 рабочих дней.

Шаг 2. Обратитесь в Жилищный комитет.
Жилищный комитет осуществляет контроль за деятельностью УК и вправе инициировать проверку, выдать предписание, обратиться в суд.

Шаг 3. Государственная жилищная инспекция (ГЖИ).
ГЖИ уполномочена проводить внеплановые проверки по обращениям граждан, выдавать предписания и привлекать УК к административной ответственности.

Шаг 4. Решение о смене управляющей компании.
Собственники вправе принять на ОСС решение о расторжении договора с УК и выборе новой организации.""",
         "Справочная служба"),
        ("faq", "Можно ли прописать в муниципальной квартире нового жильца?",
         """Регистрация (прописка) новых жильцов в муниципальной квартире возможна, однако имеет ряд ограничений по сравнению с приватизированным жильём.

Правила регистрации в муниципальном жилье:

Члены семьи нанимателя (супруг/а, дети, родители):
— регистрируются с согласия остальных совершеннолетних членов семьи, зарегистрированных в квартире;
— согласие наймодателя (Жилищного комитета) не требуется;
— ограничений по норме площади нет.

Иные граждане (не члены семьи):
— требуется согласие наймодателя (Жилищного комитета);
— соблюдение учётной нормы площади на человека (не менее 10 кв. м);
— исключение: несовершеннолетние дети регистрируются по месту проживания родителей без дополнительных условий.

Для регистрации обратитесь в МФЦ или паспортный стол с соответствующими документами.""",
         "Справочная служба"),
        ("faq", "Как рассчитывается плата за содержание жилья?",
         """Плата за содержание жилого помещения включает расходы на услуги и работы по управлению МКД, содержание и ремонт общего имущества, коммунальные ресурсы на общедомовые нужды.

Размер платы определяется:
— для собственников: решением общего собрания собственников; при отсутствии решения — тарифом, установленным органом местного самоуправления;
— для нанимателей: тарифами, утверждёнными органом местного самоуправления ежегодно.

Структура платы за содержание:
1. Управление МКД (около 10–15% от тарифа).
2. Содержание и обслуживание общего имущества: уборка подъездов, дворовой территории, вывоз ТКО.
3. Текущий ремонт: обслуживание инженерных систем, лифтов.
4. ОДН (общедомовые нужды): свет в подъездах, полив газонов и т.д.

Тарифы пересматриваются не чаще одного раза в год. Актуальные тарифы размещены на сайте Жилищного комитета.""",
         "Справочная служба"),
        ("faq", "Куда обращаться при аварии в квартире?",
         """При возникновении аварийной ситуации в квартире или доме (прорыв трубы, отключение электричества, повреждение газопровода и т.д.) необходимо действовать по следующему алгоритму:

НЕМЕДЛЕННО:
1. Газовая авария → звоните 04 (с мобильного 104) — газовая служба.
2. Пожар → звоните 01 (101) — пожарная охрана.
3. Прорыв водопровода → перекройте запорный кран в квартире, затем звоните в аварийную службу ЖКХ: 05 (105).

В рабочее время:
— обратитесь в вашу управляющую компанию.
— аварийно-диспетчерская служба УК должна отреагировать в течение 30 минут.

Круглосуточная аварийная служба Жилищного комитета: 8-800-100-10-10 (бесплатно).

После устранения аварии:
— зафиксируйте ущерб фотографиями;
— подайте заявление в УК о возмещении ущерба;
— при отказе — обратитесь в Жилищный комитет или суд.""",
         "Справочная служба"),

        # RESIDENTS
        ("residents", "Советы по энергосбережению в многоквартирном доме",
         """Снижение потребления энергоресурсов — это не только экономия для вашего кошелька, но и вклад в общее благо жильцов дома и экологию города. Жилищный комитет рекомендует следующие меры.

В квартире:
— Установите светодиодные лампы вместо ламп накаливания (экономия до 80% электроэнергии на освещение).
— Утеплите оконные и дверные проёмы в холодный период.
— Используйте приборы учёта (счётчики) для оплаты по фактическому потреблению.
— Проверяйте, не подтекают ли краны: 1 капля в секунду = 4000 литров воды в год.

В масштабах дома:
— Инициируйте на ОСС установку автоматических регуляторов теплоснабжения.
— Требуйте качественного утепления подъездов и кровли — тепловые потери через неутеплённые конструкции достигают 30%.
— Поддерживайте замену устаревшего освещения в подъездах на светодиодное с датчиками движения.""",
         "Жилищный комитет"),
        ("residents", "Правила пользования общим имуществом дома",
         """Общее имущество многоквартирного дома принадлежит собственникам квартир на праве общей долевой собственности. Это означает, что каждый из вас является сособственником лестниц, лифтов, подвалов, чердаков, крыши, придомовой территории и инженерных коммуникаций.

Основные правила:
— Запрещается захламлять и загромождать лестничные клетки и выходы из них.
— Запрещается самовольно занимать общие площади (устанавливать кладовки в подъезде, перекрывать коридоры).
— Любые изменения в составе общего имущества (перестройка, пристройка) требуют решения общего собрания.
— Содержание общего имущества осуществляется управляющей компанией в соответствии с договором управления.

Права собственников:
— пользоваться общим имуществом в установленном порядке;
— контролировать техническое состояние общего имущества;
— инициировать проверку качества содержания через Жилищный комитет.""",
         "Жилищный комитет"),
        ("residents", "Как организовать общее собрание жильцов",
         """Общее собрание собственников (ОСС) — это главный инструмент управления вашим домом. Именно на ОСС принимаются решения о выборе или смене управляющей компании, тарифах на содержание, проведении ремонтов и благоустройстве.

Как инициировать собрание:
1. Инициатор (один или несколько собственников, УК или орган местного самоуправления) разрабатывает повестку дня.
2. За 10 дней до проведения каждый собственник уведомляется письменно (заказное письмо, вручение под роспись или объявление в подъезде — если это предусмотрено договором управления).
3. В уведомлении указываются: дата, время, место, форма проведения (очная/заочная) и повестка дня.

Проведение очного собрания:
— Регистрация участников, подтверждение полномочий представителей.
— Открытие, выбор председателя и секретаря.
— Рассмотрение вопросов повестки, голосование.
— Оформление протокола в течение 10 дней.""",
         "Жилищный комитет"),
        ("residents", "Озеленение и благоустройство двора: как подать заявку",
         """Улучшение придомовой территории — дворовых пространств, детских и спортивных площадок, озеленения — во многом зависит от инициативности самих жителей. Жилищный комитет поддерживает проекты благоустройства и готов помочь их реализовать.

Способы инициировать благоустройство:

1. Через управляющую компанию.
Подайте обращение в УК с просьбой включить работы по благоустройству в план текущего ремонта. Решение принимается на ОСС.

2. Через программу «Комфортный двор».
Жилищный комитет ежегодно проводит отбор дворов для капитального благоустройства в рамках программы. Заявки принимаются с 1 марта по 1 мая. Приоритет отдаётся дворам, где жители готовы участвовать в работах (посадка деревьев, уход за газонами).

3. Инициативное бюджетирование.
Жители могут предложить проект благоустройства на конкурс инициативных проектов. При победе до 80% стоимости работ финансируется из городского бюджета.""",
         "Отдел благоустройства"),
        ("residents", "Шумные соседи: ваши права и порядок действий",
         """Нарушение тишины в многоквартирном доме — одна из самых распространённых жалоб, поступающих в Жилищный комитет. Разберёмся, как законно защитить своё право на отдых.

Нормативы тишины (в нашем регионе):
— Ночное время: с 23:00 до 7:00 — полная тишина.
— Дневной отдых: с 13:00 до 15:00 — запрет шумных работ.
— В выходные дни: ремонтные и строительные работы запрещены с 22:00 до 10:00.
— Ремонтные работы в будни допускаются с 9:00 до 19:00.

Алгоритм действий:
1. Поговорите с соседями — большинство конфликтов решается мирно.
2. Вызовите участкового уполномоченного полиции (тел. 02 или через сайт МВД).
3. Подайте жалобу в Жилищный комитет — факт нарушения фиксируется, при необходимости направляется комиссия.
4. Обратитесь в суд с исковым заявлением о компенсации ущерба (при систематических нарушениях).""",
         "Юридический отдел"),
    ]

    for section, title, content, author in articles_data:
        dt = base + timedelta(days=random.randint(0, 13))
        a = Article(title=title, content=content, section=section, author_name=author, published_at=dt)
        db.session.add(a)

    db.session.commit()


# Инициализация БД при любом запуске (в т.ч. через gunicorn)
init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
