#!/usr/bin/env python
#-*-coding:utf-8-*-

import pyodbc
import codecs
import json
from urllib import *

from utils import *
from symbol import except_clause
from virtdb import *

PREFIX = 'http://keg.tsinghua.edu.cn/movie/'
GRAPH = 'keg-movie2'
#SERVER_URL = 'http://localhost:5678/query'
SERVER_URL = 'http://10.1.1.23:5678/query'

class MovieKB():
    """
    Properties
    --------------------------
    """

    def __init__(self):
        configs = ConfigTool.parse_config("./config/db.cfg","MovieKB")
        import sys
        if re.match('linux',sys.platform):#Linux
            #self.db = JenaVirtDB(**configs)
            #self.db = OdbcVirtDB(**configs)
            configs["prefix"] = PREFIX
            configs["url"] = SERVER_URL
            self.db = HttpDB(**configs)
        else:#Windows
            #self.db = JenaVirtDB(**configs)
            configs["prefix"] = PREFIX
            configs["url"] = SERVER_URL
            self.db = HttpDB(**configs)

    def close(self):
        self.db.close()

    def fetch_one_result(self, sq):
        """
        Fetch one result from xlore virtuoso database according to query the sq string

        return:
            one result(if hits) or None(if no hit)
        """
        cursor = self._virtodb.cursor()
        results = cursor.execute(sq)
        try:
            result = results.fetchone()[0]
            if type(result) == tuple:
                result = result[0]
        except TypeError:
            return None
        finally:
            cursor.close()
        return result

    def fetch_multi_result(self, sq):
        """
        Fetch multi results from xlore virtuoso database according to query the sq string

        return:
            result list(if hits) or empty list(if no hit)
        """
        cursor = self._virtodb.cursor()
        try:
            results = [r[0] for r in cursor.execute(sq).fetchall()]
            if results and len(results) > 0 and type(results[0]) == tuple:
                results = [r[0] for r in results]
        except TypeError:
            return []
        finally:
            cursor.close()
        return results

    def get_instance_properties(self, entity_id):
        """
        Returns:
        result:dict
            k: shortcomming of property
            v: list of object
        """
        sq = 'select * from <%s> where {<%sinstance/%s> ?p ?o}'%(GRAPH, PREFIX,entity_id)
        result_set = self.db.query(sq)
        result = {}
        for p, o in result_set:
            result[p] = result.get(p,[]) + [o]
        return result

    def parse_properties(self, p2o):

        result = {}

        for p,o in p2o.items():
            key = p.split("/",5)[-1]
            result[key] = o

        return result

    def get_prop_entities(self, entity_id):

        def deep_instance(d, p):
            """
            获取instance地址下的label
            """
            s = set()
            if d.has_key(p):
                for e in d[p]:#注意value是list形式的
                    if e.startswith("http"):
                        i = e.split("/")[-1]
                        l = self.get_label(i)
                        if not l:
                            return s
                        if "[" in l:
                            s.add(l[:l.index("[")])
                        else: s.add(l)
                    else: s.add(e)
            return s

        def deep_concept(d, p):
            """
            获取concept地址下的label
            """
            s = set()
            if d.has_key(p):
                for e in d[p]: #注意value是list形式的
                    if e.startswith("http"):
                        i = e.split("/")[-1]
                        l = self.get_concept_label(i)
                        if not l:
                            return s
                        if "[" in l:
                            s.add(l[:l.index("[")])
                        else: s.add(l)
                    else: s.add(e)
            return s

        def extract_ins(d, p):
            """
            从summary和description中提取[[]]之间的实体内容
            """
            s = set()
            t = ""
            if d.has_key(p):
                for string in d[p]:#注意value是list形式的
                    while True:
                        if "[[" in string and "]]" in string:
                            start = string.index("[[") + 2
                            end = string.index("]]", start)
                            t = string[start:end]
                            s.add(t.split("||")[0])
                            string = string[end:]
                        else: break

            return s

        q_result = self.get_instance_properties(entity_id)
        d = self.parse_properties(q_result)

        es = set()
        #不能有label啊，不然肯定有共现的词
        #es.add(d["label/zh"][0])

        if not d.has_key("label/zh"):
            #连label都没有。。。扔掉！
            return es

        if d.has_key("alias"):
            es = es.union(set(d["alias"]))
        es = es.union(deep_concept(d, "instanceOf"))
        # For movie
        es = es.union(deep_instance(d,"directed_by"))
        es = es.union(deep_instance(d,"written_by"))
        es = es.union(deep_instance(d,"actor_list"))
        # For actor
        es = es.union(deep_instance(d,"work_list"))
        es = es.union(deep_instance(d,"profession/zh"))
        es = es.union(extract_ins(d, "summary"))
        es = es.union(extract_ins(d, "description/zh"))

        return es


    def get_abstract(self, entity_id):
        #sq = 'select * from <%s> where {<%sinstance/%s> <%scommon/summary> ?o }'%(GRAPH, PREFIX, entity_id, PREFIX)
        sq = 'select * from <%s> where {<%sinstance/%s> ?p ?o}'%(GRAPH, PREFIX,entity_id)
        result_set = self.db.query(sq)
        for p, o in result_set:
            if p.endswith('common/summary'):
                return o

        #return self.fetch_one_result(sq)

    def get_label(self, entity_id):
        #sq = 'select * from <%s> where {<%sinstance/%s> <%scommon/summary> ?o }'%(GRAPH, PREFIX, entity_id, PREFIX)
        sq = 'select * from <%s> where {<%sinstance/%s> ?p ?o}'%(GRAPH, PREFIX,entity_id)
        result_set = self.db.query(sq)
        for p, o in result_set:
            if p.endswith('label/zh'):
                return o

    def get_concept_label(self, entity_id):
        sq = 'select * from <%s> where {<%sinstance/%s> ?p ?o}'%(GRAPH, PREFIX,entity_id)
        result_set = self.db.query(sq)
        for p, o in result_set:
            if p.endswith('label/zh'):
                return o

    def create_littleentity(self, entity_id):

        entity = {}
        entity_id = str(entity_id)
        entity["id_"] = entity_id
        entity["uri"] = PREFIX+entity_id

        q_result = self.get_instance_properties(entity_id)

        d = self.parse_properties(q_result)

        entity["title"] = d["label/zh"][0]
        if d.has_key("alias"):
            entity["alias"] = d["alias"]
        if d.has_key("summary"):
            entity["abstract"] = d["summary"][0]
        if d.has_key("firstimage"):
            entity["image"] = d["firstimage"][0]

        return entity

    def get_entity_label(self, entity_id):
        #sq = 'select * from <%s> where { <%s> <%sobject/label/zh> ?o }'%(GRAPH, entity_id, PREFIX)
        sq = 'select * from <%s> where {<%s> ?p ?o}'%(GRAPH, entity_id)
        result_set = self.db.query(sq)
        for p, o in result_set:
            if p.endswith('label/zh'):
                return o

    def get_entity_info(self,entity_id):
        # 返回json数据
        predictmap = getPropMap()
        def get_baseinfo(entity_id,predictmap):
            result = {}
            objects= {}
            sq = 'select * from <%s> where {<%sinstance/%s> ?p ?o}'%(GRAPH, PREFIX,entity_id)
            result_set = self.db.query(sq)
            for p, o in result_set:
                p = "<%s>"%p
                if p in  predictmap['objectType']:
                    pname = predictmap['objectType'][p]
                    if pname not in result:
                        result[pname] = []

                    if o.startswith(PREFIX):
                        if pname not in objects: objects[pname]=[]
                        objects[pname].append(o)
                    else:
                        name= o
                        result[pname].append({'name':name})
                elif p in predictmap['dataType']:
                    pname = predictmap['dataType'][p]
                    if pname not in result: result[pname] = []
                    result[pname].append(o)
                elif 'instanceOf' in p:
                    if 'type' not in objects:
                        objects['type']=[o]
                        result['type']=[]
                    else: objects['type'].append(o)
            return result,objects
        result,objects = get_baseinfo(entity_id,predictmap)

        def get_objectinfo(baseinfo,objects):
            result = baseinfo
            #处理objectType信息
            for pname in objects:
                if pname == u'演员表':
                    actor_info = [{} for i in range(len(objects[u'演员表']))]
                    for uid in objects[u'演员表']:
                        sq = 'select * from <%s> where {<%s> ?p ?o}'%(GRAPH,uid)
                        result_set = self.db.query(sq)

                        actor_num = 0
                        actor_name=""
                        actor_id = ""
                        for p,o in result_set:
                            p = "<%s>"%p
                            pname = predictmap['actor_node'][p]
                            if pname == 'actor_number': actor_num = int(o) - 1
                            elif pname == 'actor_name': actor_name = o
                            elif pname == 'actor_id': actor_id = o
                        actor_info[actor_num]['name']=actor_name
                        if actor_id != "": actor_info[actor_num]['id']=actor_id
                    result[u'演员表'] = actor_info
                else:
                    for uid in objects[pname]:
                        name = self.get_entity_label(uid)
                        result[pname].append({'id':uid,'name':name})
            return result

        result =  get_objectinfo(result,objects)
        result2 = {}
        infobox = {}
        for pname in result:
            #print pname
            if pname in predictmap['common'] or pname=='type':
                result2[pname] = result[pname]
            else: infobox[pname] = result[pname]
        result2['Infoboxes'] = infobox
        return result2

    def getUriByName(self,name):
        sq = """
            select * from <keg-movie2> where {
             {?s  <http://keg.tsinghua.edu.cn/movie/object/label/zh> "%s"} union {?s  <http://keg.tsinghua.edu.cn/movie/common/alias> "%s"}
            }
            """%(name,name)
        result_set = self.db.query(sq)
        return [x[0] for x in result_set]

    #导演 演员 合作 作品  冯小刚 葛优
    def works_by_actor_director(self,aname="葛优",dname="冯小刚"):
        sq = """
            select ?m  ?o from <keg-movie2> where {
                {?fxg <http://keg.tsinghua.edu.cn/movie/common/alias> "%s".} union {?fxg <http://keg.tsinghua.edu.cn/movie/object/label/zh> "%s".}
                {?gy  <http://keg.tsinghua.edu.cn/movie/common/alias> "%s".} union {?fxg <http://keg.tsinghua.edu.cn/movie/object/label/zh> "%s".}
                ?s <http://keg.tsinghua.edu.cn/movie/blanknode/actor_id> ?gy.
                ?m <http://keg.tsinghua.edu.cn/movie/actor_list> ?s.
                ?m <http://keg.tsinghua.edu.cn/movie/directed_by> ?fxg.
                ?m <http://keg.tsinghua.edu.cn/movie/object/label/zh> ?o }
        """%(dname,dname,aname,aname)
        #result_set = self.db.query(sq)
        #return [{"id":m[0],"name":o[0]} for m,o in result_set]
        return sq

    #n年 演员a 演员b 合演作品
    def works_by_actors(self,aname1="星爷",aname2="达叔",year="91"):
        sq = """
            select ?m  ?o from <keg-movie2> where {
                {?zxc <http://keg.tsinghua.edu.cn/movie/common/alias> "%s".} union {?zxc <http://keg.tsinghua.edu.cn/movie/object/label/zh> "%s".}
                {?wmd  <http://keg.tsinghua.edu.cn/movie/common/alias> "%s".} union {?wmd <http://keg.tsinghua.edu.cn/movie/object/label/zh> "%s".}
                ?s1 <http://keg.tsinghua.edu.cn/movie/blanknode/actor_id> ?zxc.
                ?s2 <http://keg.tsinghua.edu.cn/movie/blanknode/actor_id> ?wmd.
                ?m <http://keg.tsinghua.edu.cn/movie/actor_list> ?s1.
                ?m <http://keg.tsinghua.edu.cn/movie/actor_list> ?s2.
                ?m <http://keg.tsinghua.edu.cn/movie/object/label/zh> ?o.
                {?m <http://keg.tsinghua.edu.cn/movie/tv/original_air_date> ?o} union {?m <http://keg.tsinghua.edu.cn/movie/initial_release_date> ?o}
                FILTER regex(?y, "%s", "i"
                }
            """%(aname1,aname1,aname2,aname2,year)
        #result_set = self.db.query(sq)
        #return [{"id":m[0],"name":o[0]} for m,o in result_set]
        return sq

    #作品的主演 及其 配偶
    def semantic_search_ex1(self,name="天下无贼"):
        sq = """
            select ?n ?z from <keg-movie2> where {
               {?s <http://keg.tsinghua.edu.cn/movie/common/alias> "%s".} union {?s <http://keg.tsinghua.edu.cn/movie/object/label/zh> "%s".}
                ?s <http://keg.tsinghua.edu.cn/movie/actor_list> ?ab.
                ?ab <http://keg.tsinghua.edu.cn/movie/blanknode/actor_name> ?n.
                ?ab <http://keg.tsinghua.edu.cn/movie/blanknode/actor_id> ?a.
                optional {?a <http://keg.tsinghua.edu.cn/movie/people/spouse/zh> ?z.} }
            """%(name,name)
       '''
       result_set = self.db.query(sq)
        result = []
        for m,o in result_set:
            e = {}
            e['演员']=m
            if o is not None: e['配偶']=o
            result.append(e)
        return result
        '''
        return sq

    #tvb旗下 香港出生 汉族 男 艺人
    def semantic_search_ex2(self):
        sq = """
          select ?n ?o ?nt ?p ?g from <keg-movie2> where {
            {?m <http://keg.tsinghua.edu.cn/movie/organization/company> ?o .   FILTER regex(?o, "香港无线", "i")} union
            {?m <http://keg.tsinghua.edu.cn/movie/organization/company> ?o .   FILTER regex(?o, "tvb", "i")} union
            {?m <http://keg.tsinghua.edu.cn/movie/organization/company> ?o .   FILTER regex(?o, "电视广播有限", "i")} union
            {?m <http://keg.tsinghua.edu.cn/movie/tv/produced_by_company> <http://keg.tsinghua.edu.cn/movie/instance/b10000001>.}
            ?m <http://keg.tsinghua.edu.cn/movie/object/label/zh> ?n.
            ?m <http://keg.tsinghua.edu.cn/movie/people/nationality> ?nt.
            ?m <http://keg.tsinghua.edu.cn/movie/people/birthplace> ?p.
            ?m <http://keg.tsinghua.edu.cn/movie/people/gender/zh> ?g.
            FILTER regex(?g, "男", "i")
            FILTER regex(?nt, "汉", "i")
            FILTER regex(?p, "香港", "i")
        }"""
        '''
        result_set = self.db.query(sq)
        result = []
        for name,company,nation,bplace,gender in result_set:
            e = {}
            e['名称']=name
            e['公司']=company
            e['民族']=nation
            e['出生地']=bplace
            e['性别']=gender
            result.append(e)
        return result
        '''
        return sq

if __name__ == "__main__":
    configs = ConfigTool.parse_config("./config/db.cfg","MovieKB")
    mkb = MovieKB()
    #print mkb.get_prop_entities("b10050542")
    #print mkb.getUriByName("冯小刚")
    #fw = codecs.open('test.txt','w','utf-8')
    #fw.write(json.dumps(mkb.get_entity_info("b10000001"),ensure_ascii=False))
    #fw.close()

