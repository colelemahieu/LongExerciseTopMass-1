#!/usr/bin/env python

import optparse
import os,sys
import json
import pickle
import ROOT
from subprocess import Popen, PIPE

"""
Perform the analysis on a single file
"""
def runBJetEnergyPeak(inFileURL, outFileURL, xsec=None):

    print '...analysing %s' % inFileURL

    #book some histograms
    histos={ 
        'bjeten':ROOT.TH1F('bjeten',';Energy [GeV]; Jets',30,0,300),
        'bjetenls':ROOT.TH1F('bjetenls',';log(E);  1/E dN_{b jets}/dlog(E)',20,3.,7.),
        'nvtx'  :ROOT.TH1F('nvtx',';Vertex multiplicity; Events',30,0,30),
        'nbtags':ROOT.TH1F('nbtags',';b-tag multiplicity; Events',5,0,5),
        #added
        'njets':ROOT.TH1F('njets', ';Number; Jets', 10,0,10),
        'e_pt':ROOT.TH1F('e_pt', ';Electron P_t (GeV); Electron Number', 40,0,400),
        'mu_pt':ROOT.TH1F('mu_pt',';Muon P_t (GeV); Muon Number', 40,0.,400)

        }


    for key in histos:
        histos[key].Sumw2()
        histos[key].SetDirectory(0)

    #open file and loop over events tree
    fIn=ROOT.TFile.Open(inFileURL)
    tree=fIn.Get('data')
    totalEntries=tree.GetEntriesFast()
    for i in xrange(0,totalEntries):

        tree.GetEntry(i)
        if i%100==0 : sys.stdout.write('\r [ %d/100 ] done' %(int(float(100.*i)/float(totalEntries))) )
        #require at least two jets
        nJets, nBtags, nLeptons = 0, 0, 0
        taggedJetsP4=[]
        leptonsP4=[]
        for ij in xrange(0,tree.nJet):

            #get the kinematics and select the jet
            jp4=ROOT.TLorentzVector()
            jp4.SetPtEtaPhiM(tree.Jet_pt[ij],tree.Jet_eta[ij],tree.Jet_phi[ij],tree.Jet_mass[ij])
            if jp4.Pt()<30 or ROOT.TMath.Abs(jp4.Eta())>2.4 : continue

            #count selected jet
            nJets +=1

            #save P4 for b-tagged jet
            if tree.Jet_CombIVF[ij]>0.8484: # medium cut
                nBtags+=1
                taggedJetsP4.append(jp4)


        if nJets<2 : continue
        if nBtags!=1 and nBtags!=2 : continue

        for ij in xrange(0,tree.nLepton):
            #get the kinematics and select the lepton                       
            lp4=ROOT.TLorentzVector()
            lp4.SetPtEtaPhiM(tree.Lepton_pt[ij],tree.Lepton_eta[ij],tree.Lepton_phi[ij],0)
            if lp4.Pt()<20 or ROOT.TMath.Abs(lp4.Eta())>2.4 : continue

            #count selected leptons                    
            nLeptons +=1
            leptonsP4.append(lp4)

        if nLeptons<2 : continue

        #generator level weight only for MC
        evWgt=1.0
        if xsec              : evWgt  = xsec*tree.LepSelEffWeights[0]*tree.PUWeights[0]
        if tree.nGenWeight>0 : evWgt *= tree.GenWeights[0]

        #ready to fill the histograms
        #fill nvtx plot
        histos['nvtx'].Fill(tree.nPV, evWgt)
        
        #fill nbtag plot
        histos['nbtags'].Fill(nBtags, evWgt)

        #fill njets plot
        histos['njets'].Fill(nJets, evWgt)


        #fill electron and muon plots
        for i in xrange(0,len(leptonsP4)):
            #print(leptonsP4[i].Pt())
            if i>1: break
            if abs(tree.Lepton_id[i])==11:
                histos['e_pt'].Fill(leptonsP4[i].Pt(), evWgt)
                #print(leptonsP4[i].Pt())
            if abs(tree.Lepton_id[i])==13:
                histos['mu_pt'].Fill(leptonsP4[i].Pt(), evWgt)
                #print(leptonsP4[i].Pt())

        #use up to two leading b-tagged jets
        for ij in xrange(0,len(taggedJetsP4)):
            if ij>1 : break
            histos['bjeten'].Fill(taggedJetsP4[ij].E(),evWgt)
            histos['bjetenls'].Fill(ROOT.TMath.Log(taggedJetsP4[ij].E()),evWgt/taggedJetsP4[ij].E())

    fIn.Close()

    #save histograms to file
    fOut=ROOT.TFile.Open(outFileURL,'RECREATE')
    for key in histos: histos[key].Write()
    fOut.Close()


"""
Wrapper to be used when run in parallel
"""
def runBJetEnergyPeakPacked(args):
    
    try:
        return runBJetEnergyPeak(inFileURL=args[0],
                                 outFileURL=args[1],
                                 xsec=args[2])
    except :
        print 50*'<'
        print "  Problem  (%s) with %s continuing without"%(sys.exc_info()[1],args[0])
        print 50*'<'
        return False


"""
steer the script
"""
def main():

    #configuration
    usage = 'usage: %prog [options]'
    parser = optparse.OptionParser(usage)
    parser.add_option('-j', '--json',        dest='json'  ,      help='json with list of files',      default=None,        type='string')
    parser.add_option('-i', '--inDir',       dest='inDir',       help='input directory with files',   default=None,        type='string')
    parser.add_option('-o', '--outDir',      dest='outDir',      help='output directory',             default='analysis',  type='string')
    parser.add_option('-n', '--njobs',       dest='njobs',       help='# jobs to run in parallel',    default=0,           type='int')
    (opt, args) = parser.parse_args()

    #read list of samples
    jsonFile = open(opt.json,'r')
    samplesList=json.load(jsonFile,encoding='utf-8').items()
    jsonFile.close()

    #prepare output
    if len(opt.outDir)==0    : opt.outDir='./'
    os.system('mkdir -p %s' % opt.outDir)
        
    #create the analysis jobs
    taskList = []
    for sample, sampleInfo in samplesList: 
        inFileURL = 'root://cmseos.fnal.gov//%s/%s.root' % (opt.inDir,sample)
        #if not os.path.isfile(inFileURL): continue
        xsec=sampleInfo[0] if sampleInfo[1]==0 else None        
        outFileURL = '%s/%s.root' % (opt.outDir,sample)
        taskList.append( (inFileURL,outFileURL,xsec) )

    #run the analysis jobs
    if opt.njobs == 0:
        for inFileURL, outFileURL, xsec in taskList:
            runBJetEnergyPeak(inFileURL=inFileURL, outFileURL=outFileURL, xsec=xsec)
    else:
        from multiprocessing import Pool
        pool = Pool(opt.njobs)
        pool.map(runBJetEnergyPeakPacked,taskList)

    #all done here
    print 'Analysis results are available in %s' % opt.outDir
    exit(0)



"""
for execution from another script
"""
if __name__ == "__main__":
    sys.exit(main())
