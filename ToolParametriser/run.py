#!/stornext/HPCScratch/home/iskander.j/myenvs/py3_11/bin/python

import testcreator,testresults
import tomllib
import logging,os,errno
import argparse


def main(args):
  
    if not os.path.exists(f'{os.path.expanduser("~")}/.toolparametriser/'):
        os.makedirs(f'{os.path.expanduser("~")}/.toolparametriser/')
    if not os.path.exists(args.config_path):
        logging.fatal("Config file does not exit")
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), args.config_path)
            
    with open(args.config_path, "rb") as f:
        config = tomllib.load(f)
    if args.dryrun is not None:
        config["dryrun"]=args.dryrun
    else:config["dryrun"]= False

    if args.runtype.lower()=="run":
        if config["jobs"]["tool_type"].lower()=="diann":
            test=testcreator.DiaNNTester(config=config)
        elif config["jobs"]["tool_type"].lower()=="mq":
            test=testcreator.MQTester(config=config)
        else:
            raise Exception("No accepted tooltype in config")
        if args.usetmpl is  None:  args.usetmpl=False
        test.run_test(usetmpl=args.usetmpl)

    elif args.runtype.lower()=="analyse":
        print("analyse")
        jobs_completed_file=os.path.join(config['output']['path'],"jobs_completed.csv")

        testresults.get(completed_jobs=jobs_completed_file,results_path="./allresults_1.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run/analyse a tool test')
    parser.add_argument('-c','--config_path', metavar='path', required=True,
                        help='the path to configuration file')
    parser.add_argument('-T','--usetmpl', metavar="bool", required=False,
                        help='whether to use old template if found or create a new one')
    parser.add_argument('-D','--dryrun', metavar="bool", required=False,
                        help='if true jobs will not run')
    parser.add_argument('-R','--runtype', metavar="str", required=True,
                        help='can be either [run, analyse]')
    
    
    args = parser.parse_args()
    
    main(args)