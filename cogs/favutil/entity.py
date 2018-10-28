from datetime import datetime
from typing import List

from peewee import *
from playhouse.sqlite_ext import AutoIncrementField

pragmas = {
    "foreign_keys": 1,
    "ignore_check_constraints": 0
}

db = SqliteDatabase(None)


class BaseModel(Model):
    class Meta:
        database = db


class Fav(BaseModel):
    __tablename__ = "favs"

    fav_id = AutoIncrementField()
    user_id = CharField()
    msg_id = CharField()
    server_id = CharField()
    channel_id = CharField()
    author_id = CharField()

    @classmethod
    def create(cls, msg_id, channel_id, server_id, user_id, author_id):
        return super().create(msg_id=msg_id,
                              channel_id=channel_id,
                              server_id=server_id,
                              user_id=user_id,
                              author_id=author_id)

    @classmethod
    def count_by_user(cls, user_id: str):
        return cls.select(fn.COUNT(cls.fav_id).alias("count")) \
            .where(cls.user_id == user_id) \
            .get() \
            .count

    @classmethod
    def count_untagged_by_user(cls, user_id: str):
        return cls.select(fn.COUNT(cls.fav_id).alias("count")) \
            .join(Tag, join_type=JOIN.LEFT_OUTER) \
            .where((Fav.user_id == user_id) & (Tag.tag_id.is_null())) \
            .get() \
            .count

    @classmethod
    def get_by_user(cls, user_id, tag=""):
        return cls.select() \
            .join(Tag, join_type=JOIN.LEFT_OUTER) \
            .where((cls.user_id == user_id) & ((not tag) | (Tag.tagname == tag)))

    @classmethod
    def get_by_user_and_server(cls, user_id, server_id, tag=""):
        return cls.select() \
            .join(Tag, join_type=JOIN.LEFT_OUTER) \
            .where((cls.user_id == user_id) & (cls.server_id == server_id) & ((not tag) | (Tag.tagname == tag)))

    def add_tag(self, tag: str):
        Tag.create(fav=self, tagname=tag)

    def get_tags(self):
        return Tag.select().join(Fav).where(Tag.fav == self.fav_id)

    def set_tags(self, tags: List[str]):
        self.clear_tags()
        for tag in tags:
            self.add_tag(tag)

    def clear_tags(self):
        Tag.delete().where(Tag.fav == self.fav_id).execute()

    def get_url(self):
        return "https://discordapp.com/channels/%s/%s/%s" % (self.server_id, self.channel_id, self.msg_id)

    def __repr__(self):
        return "<Fav(uid=%s, mid=%s, cid=%s, aid=%s)>" % (
            self.user_id, self.msg_id, self.channel_id, self.author_id)


class Tag(BaseModel):
    __tablename__ = "tags"

    tag_id = AutoField()
    fav = ForeignKeyField(Fav, backref='tags', on_delete="CASCADE")
    tagname = CharField()

    def __repr__(self):
        return "<Tag(fav=%i, tag=%s)>" % (self.fav.fav_id, self.tagname)


class LogEntry(BaseModel):
    __tablename__ = "favlog"

    log_id = AutoField()
    msg_id = CharField()
    channel_id = CharField()
    server_id = CharField(null=True)
    fav_id = IntegerField()
    timestamp = DateTimeField()

    @classmethod
    def create(cls, msg_id, channel_id, server_id, fav_id):
        return super().create(msg_id=msg_id,
                              channel_id=channel_id,
                              server_id=server_id,
                              fav_id=fav_id,
                              timestamp=datetime.now())

    @classmethod
    def get_by_msg_id(cls, msg_id):
        return cls.get(cls.msg_id == msg_id)

    @classmethod
    def get_by_fav_id(cls, fav_id):
        return cls.select().where(cls.fav_id == fav_id)
