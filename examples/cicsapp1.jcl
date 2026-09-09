//CICSAPP1 JOB (ACCT),'CICS REGION',CLASS=A,MSGCLASS=X
//*
//* The CICS region startup job. On a macro-era estate this file is not
//* supporting material - it is the ONLY place a file name is bound to a
//* dataset, because a DFHFCT entry carries no DSNAME. bind_jcl_region
//* reads a jcl-dependencies lineage view of it.
//*
//CICS     EXEC PGM=DFHSIP,REGION=0M,TIME=1440,
//             PARM='SI,START=AUTO,SYSIN'
//STEPLIB  DD DISP=SHR,DSN=CICSTS.SDFHAUTH
//DFHRPL   DD DISP=SHR,DSN=PROD.APP.LOADLIB
//DFHCSD   DD DISP=SHR,DSN=CICSTS.CICSAPP1.DFHCSD
//DFHTEMP  DD DISP=SHR,DSN=CICSTS.CICSAPP1.DFHTEMP
//DFHINTRA DD DISP=SHR,DSN=CICSTS.CICSAPP1.DFHINTRA
//DFHAUXT  DD DISP=SHR,DSN=CICSTS.CICSAPP1.DFHAUXT
//DFHLCD   DD DISP=SHR,DSN=CICSTS.CICSAPP1.DFHLCD
//*
//* The application files. In the CSD era these names also appear on a
//* DEFINE FILE with a DSNAME, and the two must agree; in the macro era
//* this DD is the only statement of what CUSTMAS is. APPRPT is not a
//* file at all - it is the DDNAME of the extrapartition TDQUEUE RPTQ.
//* LEGACYF matches nothing in the CSD, which is a finding, not an error:
//* a DD with no definition is either a macro-era file or dead JCL.
//*
//CUSTMAS  DD DISP=SHR,DSN=PROD.CUSTOMER.MASTER
//RATETAB  DD DISP=SHR,DSN=PROD.RATE.TABLE
//APPRPT   DD DISP=SHR,DSN=PROD.APP.REPORT
//LEGACYF  DD DISP=SHR,DSN=PROD.LEGACY.FILE
//*
//SYSIN    DD *
APPLID=CICSAPP1
SYSIDNT=APP1
GRPLIST=(APPLIST)
GMTRAN=APMN
/*
//DFHCXRF  DD SYSOUT=*
//MSGUSR   DD SYSOUT=*
//
