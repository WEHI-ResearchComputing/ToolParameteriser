from abc import ABC, abstractmethod
from datetime import datetime
import csv,json
import random,os
import logging,glob,shutil,errno
from string import Template
import xml.etree.ElementTree as ET

class AbstractTester(ABC):
    def __init__(self,config:dict) -> None:
        super().__init__()
        self.tmplfile="" #Must be set by concrete class
        self.Config=config
        if not os.path.exists(f'{os.path.expanduser("~")}/.toolparametriser/'):
            os.makedirs(f'{os.path.expanduser("~")}/.toolparametriser/')
        FORMAT = '[%(asctime)s]:%(levelname)s:%(name)s:%(message)s'
        logging.basicConfig(format=FORMAT,filename=f'{os.path.expanduser("~")}/.toolparametriser/debug.log', 
                    encoding='utf-8', level=logging.DEBUG)
        self.jobs_completed_file=os.path.join(self.Config['output']['path'],"jobs_completed.csv")
        if not os.path.exists(self.Config['output']['path']):
            os.makedirs(self.Config['output']['path'])
        if not os.path.exists(self.jobs_completed_file):
            with open(self.jobs_completed_file,'w+') as f:
                    writer = csv.writer(f)
                    writer.writerow(["jobtype","jobid","partition","numfiles","cpuspertask","mem","threads","timelimit","constraints","workingdir","extra"])
                    
        if self._validate_config():
            self.Config["Output_path"] = os.path.join(config['output']['path'],config['jobs']['tool_type']+"_"+datetime.now().strftime('%Y%m%d%H%M%S'))
            os.makedirs(self.Config["Output_path"])
            if self._validate_test_parameters():
                self._get_test_parameters()
            else:
                logging.fatal("Test Job parameters not valid")
                raise InvalidConfigObject
        else:
            logging.fatal("Config file not valid")
            raise InvalidConfigObject

    @abstractmethod
    def _create_jobscript_template(self,**kwargs):
        pass
    
    def _get_tmpl_values(self,parameters:dict,work_dir:str)->dict:
        config=self.Config
        ntasks=1
        if 'ntasks'  in parameters.keys():
            ntasks=parameters["ntasks"]
        params={
            'jobtype':f'{config["jobs"]["tool_type"]}_{config["jobs"]["run_type"]}',
            'workingdir':work_dir,
            'partition': parameters["partition"], 
            'jobname': parameters["jobname"], 
            'numfiles': parameters["numfiles"], 
            'cpuspertask': parameters["cpuspertask"], 
            'mem': parameters["mem"], 
            'threads': parameters["threads"], 
            'timelimit':parameters["timelimit"],
            'ntasks':ntasks,
            'email':config["jobs"]["email"]
        }
        params['constraints']=None
        if 'constraints'  in parameters.keys():
            params['constraints']=parameters['constraints']

        if 'inputfiles'  in parameters.keys():
            params['inputfiles']=parameters['inputfiles']
        return params

    def _run_job(self,parameters:dict,runID:str,work_dir:str):
        #Prepare values for tmpl
        params=self._get_tmpl_values(parameters,work_dir) 
        #Substitute Tmpl 
        with open(os.path.join(self.Config["Output_path"],self.tmplfile), 'r') as f:
            template = Template(f.read())
            result = template.safe_substitute(params)
        #Save to file
        with open(os.path.join(self.Config["Output_path"],runID,"batch.slurm"), 'w') as f:
            f.write(result)
        #RUN if not dryrun
        if not self.Config["dryrun"]:
                os.system(f"cd {os.path.join(self.Config['Output_path'],runID)};"+ 
                    f"sbatch {os.path.join(self.Config['Output_path'],runID,'batch.slurm')}")
           
    ##TODO validate_config
    def _validate_config(self)->bool:

        return True
    ## TODO validate_test_parameters
    def _validate_test_parameters(self)->bool:

        return True

    def _get_test_parameters(self):
        try:
            with open(self.Config['jobs']['params_path'], "r") as file:
                self.Config["job_parameters"]=list(csv.DictReader(file))
        except IOError:
            if IOError.errno == errno.EACCES:
                logging.fatal("Test parameters file exists, but isn't readable")
            elif IOError.errno == errno.ENOENT:
                logging.fatal("Test parameters file isn't readable because it isn't there")
                raise IOError
    
    def __prepare_run_dir(self,runID:str,params:dict) -> str:
        outpath=os.path.join(self.Config["Output_path"],runID)
        os.makedirs(outpath)
        allinputfiles = glob.glob(self.Config['input']['path'], recursive=False)
        runfiles = random.sample(allinputfiles, k=int(params["numfiles"]))
        for runfile in runfiles:
            name_of_folder = runfile.split("/")[-1]
            try:
                shutil.copytree(runfile, 
                            os.path.join(outpath,name_of_folder), 
                            dirs_exist_ok=True)
            except NotADirectoryError:
                shutil.copy(runfile, os.path.join(outpath,name_of_folder))
        if "extra" in self.Config:
            for extrafile in self.Config["extra"]:
                shutil.copy(extrafile["path"],outpath)
        
        return outpath

    #Accessible Function
    def run_test(self):    
        self._create_jobscript_template()    
        if self._validate_test_parameters():
            for parameters in self.Config["job_parameters"]:
                for rep in range(self.Config["jobs"]["num_reps"]):
                    runID = f"repo-{parameters['jobname']}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    outpath=self.__prepare_run_dir(runID=runID,params=parameters)
                    self._run_job(runID=runID,parameters=parameters,work_dir=outpath)
            with open(os.path.join(self.Config["Output_path"],'config.json'), 'w') as cfile:
                cfile.write(json.dumps(self.Config))
        else:
            logging.fatal("Test Parameters file not valid.")
            raise InvalidTestParameters

class MQTester(AbstractTester):
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.tmplfile="MQtemplate.tmpl"
        config["jobs"]["run_type"]=""
    
    def _run_job(self,runID,parameters,work_dir):
        self.__update_xml(runID ,parameters)
        super()._run_job(runID=runID,parameters=parameters,work_dir=work_dir)

    def _create_jobscript_template(self,**kwargs):
        with open(os.path.join(self.Config["Output_path"],self.tmplfile), "w+") as fb:
            fb.writelines("#!/bin/bash\n")
            fb.writelines("#SBATCH -p ${partition}\n")
            fb.writelines("#SBATCH --job-name=${jobname}\n")
            fb.writelines("#SBATCH --ntasks=${ntasks}\n")
            fb.writelines("#SBATCH --time=${timelimit}\n")
            fb.writelines("#SBATCH --cpus-per-task=${cpuspertask}\n")
            fb.writelines("#SBATCH --mem=${mem}G\n")
            fb.writelines("#SBATCH --output=slurm-%j.out\n")
            fb.writelines("#SBATCH --mail-type=ALL,ARRAY_TASKS\n")
            fb.writelines("#SBATCH --mail-user=${email}\n")
           
            fb.writelines("#SBATCH --constraint=${constraints}\n")

            fb.writelines("module load MaxQuant/2.0.2.0\n")
            fb.writelines("/stornext/System/data/apps/rc-tools/rc-tools-1.0/bin/tools/MQ/createMQXML.py ${threads}\n")
            fb.writelines("MaxQuant mqpar.mod.xml\n")

            fb.writelines(
                'echo \"${jobtype},$SLURM_JOB_ID,${partition},${numfiles},${cpuspertask},${mem},${threads},${timelimit},${constraints},${workdir},\" >> '+f'{self.jobs_completed_file}\n'
            )

    def _validate_config(self) -> bool:
        valid = super()._validate_config()
        if not any(d.get('name', "") == 'xml' for d in self.Config["extra"]) or not any(d.get('name', "") == 'fasta' for d in self.Config["extra"]):
            valid=False
        if not self.Config["jobs"]["tool_type"]=="MQ":
            valid=False
        return valid

    """
    Method specific to MQ only, to update XML file
    """   
    def __update_xml(self,runID:str,parameters:dict) -> None:
        xml_path=next(item['path'] for item in self.Config["extra"] if item["name"] == "xml")
        if not os.path.exists(xml_path):
            logging.error(f"No xml file found.")
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), xml_path)
        else:
            tree = ET.parse(xml_path)
            outputfile=os.path.join(self.Config["Output_path"],runID,"mqpar.mod.xml")
            root = tree.getroot()
            numfiles=0
            for filepath_tag in root.findall('filePaths/string'):
                winpath=filepath_tag.text
                if winpath != None:
                    linuxpath=os.path.join(self.Config["Output_path"],runID,winpath.split("\\")[-1])
                    if(os.path.exists(linuxpath)):
                        logging.debug(f"{linuxpath} exists")
                        filepath_tag.text=linuxpath
                        logging.info(f"Updating filepath : {linuxpath}")
                        numfiles=numfiles+1
                    else:
                        root.findall('filePaths')[0].remove(filepath_tag)
            logging.info(f"Updated {numfiles} files.")
            winfastapath=root.findall('fastaFiles/FastaFileInfo/fastaFilePath')[0].text
            if winfastapath != None:
                linuxfastapath=os.path.join(os.path.abspath(os.getcwd()),winfastapath.split("\\")[-1])
            
                logging.info(f"Updating fastapath : {linuxfastapath}")
                if(os.path.exists(linuxfastapath)):
                        root.findall('fastaFiles/FastaFileInfo/fastaFilePath')[0].text=linuxfastapath
            
            #<useDotNetCore>True</useDotNetCore>
            root.findall('useDotNetCore')[0].text="True"
            #<numThreads>8</numThreads>
            numthreads=parameters["threads"]
            numthreads = numfiles if (numfiles != 0) and (numthreads==0) else numthreads
            root.findall('numThreads')[0].text=str(numthreads)
            logging.info(f"Threads set to {numthreads}.")
            logging.info(f"Saving new xml file : {outputfile}")
            tree.write(outputfile)

class InvalidConfigObject(Exception):
    "Raised when config object is not valid, or have missing fields"
    def __init__(self, message="Config object or Job parameters object is not valid, or have missing fields. See logs in ~/.toolparametriser/"):
        self.message = message
        super().__init__(self.message)
class InvalidTestParameters(Exception):
    "Raised when Test Parameters file is not valid, or have missing fields"
    def __init__(self, message="Test Parameters file is not valid, or have missing fields. See logs in ~/.toolparametriser/"):
        self.message = message
        super().__init__(self.message)

class DiaNNTester(AbstractTester):
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.tmplfile="DiaNNtemplate.tmpl"
        self.inputfiles=[]

    def _validate_config(self) -> bool:
        valid = super()._validate_config()
        if not self.Config["jobs"]["tool_type"]=="DiaNN":
            return False
        if self.Config["jobs"]["run_type"]=="lib":
            if not any(d.get('name', "") == 'tsv' for d in self.Config["extra"]) or not any(d.get('name', "") == 'fasta' for d in self.Config["extra"]):
                return False
        elif not any(d.get('name', "") == 'fasta' for d in self.Config["extra"]):
                return False
        if not self.Config["jobs"]["tool_type"]=="DiaNN":
            valid=False
        return valid

    def _run_job(self,runID,parameters,work_dir):
        parameters['inputfiles']=' --f '.join(self.__get_input_files(runID=runID))
        super()._run_job(runID=runID,parameters=parameters,work_dir=work_dir)

    def _create_jobscript_template(self,**kwargs):
        with open(os.path.join(self.Config["Output_path"],self.tmplfile), "w+") as fb:
            fb.writelines("#!/bin/bash\n")
            fb.writelines("#SBATCH -p ${partition}\n")
            fb.writelines("#SBATCH --job-name=${jobname}\n")
            fb.writelines("#SBATCH --ntasks=${ntasks}\n")
            fb.writelines("#SBATCH --time=${timelimit}\n")
            fb.writelines("#SBATCH --cpus-per-task=${cpuspertask}\n")
            fb.writelines("#SBATCH --mem=${mem}G\n")
            fb.writelines("#SBATCH --output=slurm-%j.out\n")
            fb.writelines("#SBATCH --mail-type=ALL,ARRAY_TASKS\n")
            fb.writelines("#SBATCH --mail-user=${email}\n")
           
            fb.writelines("#SBATCH --constraint=${constraints}\n")
            fb.writelines("module use /stornext/System/data/modulefiles/sysbio\n")
            fb.writelines("module load DiaNN/1.8\n")
            fb.writelines("diann-1.8 ")
            fb.writelines(" --f ${inputfiles} --lib \"${lib}\"")
            fb.writelines("--threads ${threads} --verbose 4 ")
            fb.writelines(" --fasta \"${fastafile}\" ")
            fb.writelines(" ${args} \n")
            
            fb.writelines(
                'echo \"${jobtype},$SLURM_JOB_ID,${partition},${numfiles},${cpuspertask},${mem},${threads},${timelimit},${constraints},${workingdir},type=${type}\" >> '+f'{self.jobs_completed_file}\n'
            )
    """ 
    Method specific to Diann only
    """  
    def __get_input_files(self,runID:str)->list:
        outpath=os.path.join(self.Config["Output_path"],runID,self.Config["input"]["ext"])
        return glob.glob(outpath, recursive=False)

    '''Overriding get_tmpl_values to add input files'''   
    def _get_tmpl_values(self,parameters:dict,work_dir:str)->dict:
        params=super()._get_tmpl_values(parameters=parameters,work_dir=work_dir)
        if 'inputfiles'  in parameters.keys():
            params['inputfiles']=parameters['inputfiles']

        params['type']=self.Config["jobs"]["run_type"]
        if params['type']=="lib":
            params['lib']=next(item['path'] for item in self.Config["extra"] if item["name"] == "tsv")
            params["args"]="".join([
            " --out \"./outputreport.tsv\" ",
            " --qvalue 0.01 --matrices  --out-lib \"./spectrallib.tsv\" ",
            " --gen-spec-lib --predictor --met-excision --cut \"K*,R*\" --mass-acc 10 --mass-acc-ms1 10.0 --use-quant --reanalyse",
            
            " --smart-profiling --peak-center --no-ifs-removal \n"])
            
        elif params['type']=="libfree":
            params['lib']=""
            params["args"]="".join([
            " --out \"./outputreport.tsv\" ",
            " --qvalue 0.01 --matrices  --out-lib \"./spectrallib.tsv\" --gen-spec-lib --predictor --fasta-search  ",
            " --min-fr-mz 200 --max-fr-mz 1800 --met-excision --use-quant  ",
            " --cut \"K*,R*\" --missed-cleavages 1 --min-pep-len 7 --max-pep-len 30 --min-pr-mz 300  ",
            " --max-pr-mz 1800 --min-pr-charge 1 --max-pr-charge 4 --mass-acc 10 --mass-acc-ms1 10.0  ",
            " --reanalyse --smart-profiling --peak-center --no-ifs-removal"])

        params['fastafile']=next(item['path'] for item in self.Config["extra"] if item["name"] == "fasta")
        return params

class InlineGeneric(AbstractTester):
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.tmplfile="Generictemplate.tmpl"
    def  _create_jobscript_template(self,**kwargs):
        with open(os.path.join(self.Config["Output_path"],self.tmplfile), "w+") as fb:
            fb.writelines("#!/bin/bash\n")
            fb.writelines("#SBATCH -p ${partition}\n")
            fb.writelines("#SBATCH --job-name=${jobname}\n")
            fb.writelines("#SBATCH --ntasks=${ntasks}\n")
            fb.writelines("#SBATCH --time=${timelimit}\n")
            fb.writelines("#SBATCH --cpus-per-task=${cpuspertask}\n")
            fb.writelines("#SBATCH --mem=${mem}G\n")
            fb.writelines("#SBATCH --output=slurm-%j.out\n")
            fb.writelines("#SBATCH --mail-type=ALL,ARRAY_TASKS\n")
            fb.writelines("#SBATCH --mail-user=${email}\n")
           
            fb.writelines("#SBATCH --constraint=${constraints}\n")

            fb.writelines("${modules}\n")
            if 'cmd' in self.Config["jobs"]:
                fb.writelines(f"{self.Config['jobs']['cmd']}\n")
            
            fb.writelines(
                'echo \"${jobtype},$SLURM_JOB_ID,${partition},${numfiles},${cpuspertask},${mem},${threads},${timelimit},${constraints},${workingdir},type=${type}\" >> '+f'{self.jobs_completed_file}\n'
            )
    
    def _run_job(self,runID,parameters,work_dir):
        
        super()._run_job(runID=runID,parameters=parameters,work_dir=work_dir)

    def _get_modules(self):
        modules_str=""
        if "modules" in self.Config:
            for mod in self.Config["modules"]:
                if "use" in mod:
                    modules_str+=f"module use {mod['use']}\n"
                if "name" in mod:
                    modules_str+=f"module load {mod['name']}\n"
        return modules_str




    '''Overriding get_tmpl_values'''   
    def _get_tmpl_values(self,parameters:dict,work_dir:str)->dict:
        params=super()._get_tmpl_values(parameters=parameters,work_dir=work_dir)
        params["modules"]=self._get_modules()
        if "cmd_placeholder" in self.Config:
            for placeholder in self.Config["cmd_placeholder"]:
                if "name" in placeholder and "path" in placeholder:
                    params[placeholder["name"]]=placeholder["path"]
        return params    
    