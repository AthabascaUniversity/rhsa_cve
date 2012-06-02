#!/usr/bin/python

from __future__ import print_function

import sys
import os, os.path
import urllib2
import datetime

import argparse
import gzip
import csv
import re

from UserDict import UserDict

from xml.dom.minidom import parse as minidom_parse
# from xml.etree.ElementTree import ElementTree

                                                                                                                     
## Based on information at:                                                                                          
##  https://www.redhat.com/security/data/metrics/                                                                    
##  http://cve.mitre.org/                                                                                            
                                                                                                                     
CVE_ALLITEMS_GZ_URL='http://cve.mitre.org/data/downloads/allitems.csv.gz'
RHSA_MAP_CPE_TXT_URL='https://www.redhat.com/security/data/metrics/rhsamapcpe.txt'
CPE_DICT_URL='https://www.redhat.com/security/data/metrics/cpe-dictionary.xml'

def fetch(url,filename,force=False):
    if not os.path.exists(filename) or force:
        # fetch CVE stuff
        print("Fetching {0} from {1}".format(filename,url))
        remote=urllib2.urlopen(url)
        local=open(filename,'w')
        can=True
        while can:
            buf=remote.read(1024)
            if buf:
                local.write(buf)
            else:
                can=False
        remote.close()
        local.close()

def isEmpty(my_list):
    for i in my_list:
        if i:
            return False
    return True

class MissingArguments(object):
    def __init__(self,text):
        self.text=text
    def __str__(self):
        return self.text

class Rhsa2CveMap(UserDict):

    _filter=None
    _cpe_filter=None
    
    def __init__(self,filename=None):
        UserDict.__init__(self)
        if filename:
            self.load(filename)
        self._filter=None

    def setLoadFilter(self,filter):
        """List only items that match filter"""
        self._filter=filter

    def setLoadCPEFilter(self,filter):
        """List only items that fuzzy-match filter:
        start with the same string"""
        self._cpe_filter=filter



    def load(self,filename):
        if self._filter:
            # set is going to be better in managing tasks we have at hand
            filter_set=set(self._filter)
        else:
            filter_set=False
        
        with open(filename,'r') as f:
            for line in f:
                (rhsa,cve_list,cpe_list)=line.split()
                rhsa_dict={}
                cve=cve_list.split(',')
                if self._filter:
                    cve_set=set(cve)
                    if filter_set.isdisjoint(cve_set):
                        continue
                    else:
                        cve=list(cve_set.intersection(filter_set))
                    
                cpe=[]
                cpe_raw=cpe_list.split(',')
                for c in cpe_raw:
                    # print(c)
                    filterOut=True
                    if self._cpe_filter:
                        for cf in self._cpe_filter:
                            if c[:len(cf)] == cf:
                                filterOut=False
                                print('Found {0} matching {1}'.format(c,cf))
                                break
                    else:
                        filterOut=False
                    if filterOut:
                        continue
                    elements=c.split(':')
                    try:
                        ed,package=elements[-1].split('/')
                    except ValueError:
                        ed=elements[-1]
                        package=None
                        print("ERROR: can't parse: ",c)
                        continue
                    t=elements[:-1]+[ed]
                    cpe_lookup=":".join(t)
                    cpe_dict={'base':cpe_lookup,'uri':c,'package':package}
                    cpe.append(cpe_dict)
                    
                rhsa_dict['CPE']=cpe
                rhsa_dict['CVE']=cve
                self.data[rhsa]=rhsa_dict

class CVEList(UserDict):
    _filter=None
    def __init__(self,filename=None):
        UserDict.__init__(self)
        if filename:
            self.load(filename)
            
        self._filter=None
        self._ref_re=re.compile(r' +\| +')

    def setLoadFilter(self,filter):
        """List only items that match filter"""
        self._filter=filter

    def load(self,filename):
        with open(filename,'r') as f:
            self._load(f)
    
    def load_gz(self,filename):
        with gzip.open(filename,'r') as f:
            self._load(f)
        

    def _load(self,file):
        reader=csv.reader(file)
        ## 1. read line #3  for field names
        ## 2. read the rest of the file after empty line
        
        while reader.line_num<3:
            row=reader.next()

        base_dict=row
        # print( base_dict)
        
        while not isEmpty(row):
            row=reader.next()
            
        # now we're at empty row
        
        for row in reader:
            # print(row[0])
            cve_id=row[0]
            if self._filter:
                # print("filter...")
                if not (cve_id in self._filter):
                    continue
            raw_dict=dict(zip(base_dict,row))
            ref_list=self._ref_re.split(raw_dict['References'])
            raw_dict['References']=ref_list
            self.data[cve_id]=dict(zip(base_dict,row))

class CPEDict(UserDict):
    """CPE dictionary object"""
    _filter=None
    def __init__(self,filename=None):
        UserDict.__init__(self)
        if filename:
            self.load(filename)
            
        self._filter=None

    def setLoadFilter(self,filter):
        self._filter=filter
        
    def load(self,filename):
        # cpe_tree=ElementTree()
        # cpe_list=cpe_tree.parse(filename)
        cpe_list=minidom_parse(filename)

        # print(cpe_list)
        for ci in cpe_list.getElementsByTagName('cpe-item'):
            # print('found item')
            ci_title_elem=ci.getElementsByTagName('title')[0]
            self.data[ci.getAttribute("name")]=ci_title_elem.firstChild.nodeValue
            
class CveRhsaAnalyzer(object):

    _cve_dict=None
    _cpe_dict=None
    _rhsa2cve_dict=None
    
    def __init__(self,cve,rhsa2cve,cpe):
        self.setCpeDict(cpe)
        self.setCveDict(cve)
        self.setRhsa2CveDict(rhsa2cve)

    def setCveDict(self,cve):
        self._cve_dict=cve
        
    def setCpeDict(self,cpe):
        self._cpe_dict=cpe
        
    def setRhsa2CveDict(self,rhsa2cve):
        self._rhsa2cve_dict=rhsa2cve
    
    def get_cve_compliance_report(self):
        """Map out CVE->RHSA with attached package names affected
        Returns tuple: (CVE-ID:str,Fixed:bool,RHSA:list,pkgs:set)"""
        #TODO add ability to generate package->CVE list for automated checking  
        cve=self._cve_dict
        cpe=self._cpe_dict
        rhsa2cve=self._rhsa2cve_dict
        
        rev_map={}
        for rhsa in rhsa2cve.keys():
            cve_list=rhsa2cve[rhsa]['CVE']
            for c in cve_list:
                if rev_map.has_key(c):
                    rev_map[c].append(rhsa)
                else:
                    rev_map[c]=[rhsa]
            # print(rhsa, ",".join(cve_list))
        report=[]
        for cve_name in cve.keys():
            if rev_map.has_key(cve_name):
                rev_lookup=rev_map[cve_name]
                # print(rev_lookup)
                pkg_set=set()
                for r in rev_lookup:
                    cpe_list=rhsa2cve[r]['CPE']
                    for cpe_item in cpe_list:
                        pkg_set.add(cpe_item['package'])
                # print(cve_name,",".join(rev_lookup),",".join(pkg_list))
                report.append((cve_name,True,rev_lookup,pkg_set))
            else:
                # print(cve_name,"NOT FIXED")
                report.append((cve_name,False,(),()))
        return report
        
    def get_package_cve_map(self,cve_report=None):
        """create a list of packages with CVE items to check"""
        # we need something we can use for meta-loop:
        # for p in packages:
        #   login to server
        #   rpm --changelog -q $p | grep $cve 
        cve=self._cve_dict
        cpe=self._cpe_dict
        rhsa2cve=self._rhsa2cve_dict
        pkg_dict={}
        if not cve_report:
            cve_report=self.get_cve_compliance_report()
        for (cve_id,status,rhsa,pkg_set) in cve_report:
            if status:
                for p in pkg_set:
                    if not pkg_dict.has_key(p):
                        pkg_dict[p]=[]
                    pkg_dict[p].append(cve_id)
        return pkg_dict

class CheckApplication(object):

    _cve_candidates_filename=None
    _cve_dict=None
    _cpe_dict=None
    _rhsa2cve_dict=None

    _failed_csv_filename=None
    _fixed_list_filename=None

    def createParser(self):
        parser = argparse.ArgumentParser(description='RHSA & CVE cross-reference tool')
        parser.add_argument('cve_candidates',type=str,help="name of the file listing CVE's",
                             metavar='<cve_list_file>', default=None)
        return parser

    def setupFiles(self):
        today=datetime.date.today()
        today_str=today.strftime('%Y-%m-%d')
        cve_csv_filename='cve-allitems-'+today_str+'.csv'
        cve_csv_gz_filename='cve-allitems-'+today_str+'.csv.gz'
        rhsa2cve_filename='rhsamapcpe-'+today_str+'.txt'
        cpe_dict_filename='cpe-dictionary.xml'
        
        # print(a)
        # print(cve_filter)
    
        self._failed_csv_filename='compiled/failed-'+today_str+'.csv'
        self._fixed_list_filename='compiled/fixed-'+today_str+'.txt'
    
        try:
            os.mkdir('compiled')
        except OSError:
            # directory exists, it's fine
            pass
    
        fetch(CVE_ALLITEMS_GZ_URL,cve_csv_gz_filename)
        fetch(RHSA_MAP_CPE_TXT_URL,rhsa2cve_filename)
        fetch(CPE_DICT_URL,cpe_dict_filename)
        return (cve_csv_gz_filename,rhsa2cve_filename,cpe_dict_filename)
        
    def __init__(self,argv):
         
        parser=self.createParser()
        args = parser.parse_args(argv[1:])

        if args.cve_candidates:
            self._cve_candidates_filename=args.cve_candidates
        else:
            self._cve_candidates_filename='need_to_fix'
            
        (cve_csv_gz_filename,rhsa2cve_filename,cpe_dict_filename)=self.setupFiles()

        with open(self._cve_candidates_filename,'r') as f:
            cve_list_str=f.read()
        
        # all we have to do is split giant string
        # into CVE items:
        cve_filter=cve_list_str.split()

        cpe=CPEDict(cpe_dict_filename)
        cve=CVEList()
        cve.setLoadFilter(cve_filter)
        cve.load_gz(cve_csv_gz_filename)
        rhsa=Rhsa2CveMap()
        rhsa.setLoadFilter(cve_filter)
        # rhsa.setLoadCPEFilter(['cpe:/o:redhat:enterprise_linux'])
        rhsa.load(rhsa2cve_filename)
        
        self._cpe_dict=cpe
        self._cve_dict=cve
        self._rhsa2cve_dict=rhsa

        
    def printCveReport(self,cra=None,cve_report=None):
        (cve,rhsa,cpe)=(self._cve_dict,self._rhsa2cve_dict,self._cpe_dict)

        if cra:
            cr=cra
        else:
            cr=CveRhsaAnalyzer(cve,rhsa,cpe)
        
        if cve_report:
            report=cve_report
        else:
            report=cr.get_cve_compliance_report()
        for (cve_id,status,rhsa_list,pkg_list) in report:
            if status:
                print(cve_id,",".join(rhsa_list),",".join(pkg_list))
            else:
                print(cve_id,'NOT FIXED')
                
        pkg_cve=cr.get_package_cve_map(report)
        print(pkg_cve)

##### SHELL ######
#===============================================================================
# 
# echo ""> $fixed_list
# # we need line #3 with header...
# sed -n '3p' ${cve_csv} > $failed_csv
# 
# for cve in $(cat ${cve_candidates}) 
#  do 
#   if grep $cve ${rhsa2cve_file} >> $fixed_list 
#      then
#        echo "===> $cve OK"
#      else
#        echo "===> $cve FAILED"
#        grep $cve ${cve_csv} >> $failed_csv
#   fi
#  done 
#===============================================================================
        
    def createCveReportFiles(self,cra=None,cve_report=None):
        (cve,rhsa,cpe)=(self._cve_dict,self._rhsa2cve_dict,self._cpe_dict)

        if cra:
            cr=cra
        else:
            cr=CveRhsaAnalyzer(cve,rhsa,cpe)
        
        if cve_report:
            report=cve_report
        else:
            report=cr.get_cve_compliance_report()
            
        writer=csv.writer(open(self._failed_csv_filename, 'wb'),quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow(["Name","Status","Description","Phase","Comments"])
        for (cve_id,status,rhsa_list,pkg_list) in report:
            if not status:
                cve_item=cve[cve_id]
                writer.writerow((cve_id,cve_item["Status"],cve_item["Description"],cve_item["Phase"],cve_item["Comments"]))
        
        with open(self._fixed_list_filename,'w') as f:
            for (cve_id,status,rhsa_list,pkg_list) in report:
                if status:
                    print(cve_id,",".join(rhsa_list),",".join(pkg_list),file=f)
        

if __name__ == '__main__':
    ca=CheckApplication(sys.argv)
    ca.printCveReport()
    ca.createCveReportFiles()

